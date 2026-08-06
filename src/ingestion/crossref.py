from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from html import unescape
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, now_utc, read_json, write_json


CROSSREF_API_URL = "https://api.crossref.org/works"
REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_ATTEMPTS = 4
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
USER_AGENT = "Day10DataObservabilityLab/1.0 (educational data pipeline)"


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return normalize_whitespace(str(value)) if value is not None else ""


def _clean_markup_text(value: Any) -> str:
    text = _first_text(value)
    if not text:
        return ""
    # Crossref abstracts commonly contain JATS/XML tags such as <jats:p>.
    without_tags = re.sub(r"<[^>]+>", " ", unescape(text))
    return normalize_whitespace(without_tags)


def _request_metadata_path(settings: Settings) -> Path:
    """Return the provenance path while tolerating lightweight test settings."""
    configured_path = getattr(settings.paths, "raw_request_metadata", None)
    if configured_path is not None:
        return Path(configured_path)
    return settings.paths.raw_api_response.with_name("crossref_request.json")


def _date_from_parts(value: Any) -> str:
    if not isinstance(value, dict):
        return ""

    date_time = value.get("date-time")
    if isinstance(date_time, str) and date_time:
        return date_time[:10]

    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not parts[0]:
        return ""

    try:
        year = int(parts[0][0])
        month = int(parts[0][1]) if len(parts[0]) > 1 else 1
        day = int(parts[0][2]) if len(parts[0]) > 2 else 1
        return date(year, month, day).isoformat()
    except (TypeError, ValueError):
        return ""


def _first_available_date(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        parsed = _date_from_parts(item.get(key))
        if parsed:
            return parsed
    return ""


def _parse_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    authors: list[str] = []
    for author in value:
        if not isinstance(author, dict):
            continue
        name = _first_text(author.get("name"))
        if not name:
            name = normalize_whitespace(
                " ".join(part for part in (_first_text(author.get("given")), _first_text(author.get("family"))) if part)
            )
        if name and name not in authors:
            authors.append(name)
    return authors


def _parse_categories(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    categories: list[str] = []
    for raw_category in value:
        category = _first_text(raw_category)
        if category and category not in categories:
            categories.append(category)
    return categories


def _find_pdf_url(item: dict[str, Any]) -> str:
    links = item.get("link")
    if not isinstance(links, list):
        return ""
    for link in links:
        if not isinstance(link, dict):
            continue
        url = _first_text(link.get("URL"))
        content_type = _first_text(link.get("content-type")).lower()
        if url and (content_type == "application/pdf" or url.lower().endswith(".pdf")):
            return url
    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref response into a stable raw-record contract.

    A usable record must have a DOI, title and abstract. Duplicate DOIs are
    removed at the source boundary so ``paper_id`` remains stable downstream.
    """
    if not isinstance(payload, dict):
        raise ValueError("Crossref payload must be a JSON object.")

    message = payload.get("message")
    items = message.get("items") if isinstance(message, dict) else None
    if not isinstance(items, list):
        raise ValueError("Crossref payload is missing message.items.")

    records: list[PaperRecord] = []
    seen_paper_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = _first_text(item.get("DOI")).lower()
        title = _clean_markup_text(item.get("title"))
        summary = _clean_markup_text(item.get("abstract"))
        if not paper_id or not title or not summary or paper_id in seen_paper_ids:
            continue

        categories = _parse_categories(item.get("subject"))
        abs_url = _first_text(item.get("URL"))
        if not abs_url:
            resource = item.get("resource")
            primary = resource.get("primary") if isinstance(resource, dict) else None
            abs_url = _first_text(primary.get("URL")) if isinstance(primary, dict) else ""

        comment_parts = [
            _first_text(item.get("publisher")),
            _first_text(item.get("container-title")),
        ]
        record = PaperRecord(
            paper_id=paper_id,
            title=title,
            summary=summary,
            authors=_parse_authors(item.get("author")),
            categories=categories,
            primary_category=categories[0] if categories else "",
            published=_first_available_date(
                item,
                ("published-print", "published-online", "published", "issued"),
            ),
            updated=_first_available_date(item, ("indexed", "deposited", "created")),
            abs_url=abs_url,
            pdf_url=_find_pdf_url(item),
            comment="; ".join(part for part in comment_parts if part),
        )
        records.append(record)
        seen_paper_ids.add(paper_id)

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref records, preserve the source snapshot, and parse it.

    Transient HTTP and network failures are retried with exponential backoff.
    The unmodified response is written before parsing so malformed upstream
    data remains traceable.
    """
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    response: requests.Response | None = None
    last_error: Exception | None = None
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            response = requests.get(
                CROSSREF_API_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                break

            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2**attempt
            time.sleep(delay)
        except requests.HTTPError as exc:
            last_error = exc
            status_code = response.status_code if response is not None else None
            if status_code not in RETRYABLE_STATUS_CODES:
                raise RuntimeError(f"Crossref request failed with HTTP status {status_code}.") from exc
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise RuntimeError(
                    f"Crossref request failed after {MAX_REQUEST_ATTEMPTS} attempts."
                ) from exc
        except requests.RequestException as exc:
            last_error = exc
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise RuntimeError(
                    f"Crossref request failed after {MAX_REQUEST_ATTEMPTS} attempts."
                ) from exc
            time.sleep(2**attempt)
    else:  # pragma: no cover - defensive guard for future loop changes
        raise RuntimeError("Crossref request did not produce a response.") from last_error

    if response is None:  # pragma: no cover - keeps type and failure mode explicit
        raise RuntimeError("Crossref request did not produce a response.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Crossref returned a non-JSON response.") from exc

    fetched_at = now_utc().isoformat()
    write_json(settings.paths.raw_api_response, payload)
    records = parse_crossref_payload(payload)
    if not records:
        raise ValueError("Crossref response contained no usable paper records.")
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    message = payload.get("message") if isinstance(payload, dict) else None
    api_items = message.get("items") if isinstance(message, dict) else None
    write_json(
        _request_metadata_path(settings),
        {
            "source": settings.source_api,
            "endpoint": CROSSREF_API_URL,
            "fetched_at_utc": fetched_at,
            "request": params,
            "http_status": response.status_code,
            "api_items": len(api_items) if isinstance(api_items, list) else None,
            "usable_records": len(records),
            "artifacts": {
                "raw_response": str(settings.paths.raw_api_response),
                "raw_records": str(settings.paths.raw_records_json),
            },
        },
    )
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a parsed JSON snapshot and restore the ``PaperRecord`` objects."""
    if not path.exists():
        raise FileNotFoundError(f"Raw records snapshot does not exist: {path}")

    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Raw records snapshot must contain a JSON list: {path}")

    records: list[PaperRecord] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Raw record at index {index} is not a JSON object.")
        try:
            record = PaperRecord(**item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Raw record at index {index} does not match PaperRecord schema.") from exc
        if not isinstance(record.authors, list) or not isinstance(record.categories, list):
            raise ValueError(f"Raw record at index {index} has invalid list fields.")
        records.append(record)

    if not records:
        raise ValueError(f"Raw records snapshot is empty: {path}")
    return records
