from __future__ import annotations

from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
import os
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_API_URL = "https://api.crossref.org/works"
CROSSREF_SORT = "relevance"
CROSSREF_ORDER = "desc"
MARKUP_STRIP_PASSES = 3
REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_TAG_PATTERN = re.compile(r"<[^>]+>")
_ABSTRACT_LABEL_PATTERN = re.compile(r"^\s*abstract[:\s]*", flags=re.IGNORECASE)


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


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return normalize_whitespace(unescape(value))


def _strip_markup(value: Any) -> str:
    """Bo JATS/XML markup. Crossref co the escape long nhau (`&lt;jats:p&gt;`),
    nen phai lap strip-tag + unescape cho toi khi on dinh."""
    if not isinstance(value, str):
        return ""
    text = value
    for _ in range(MARKUP_STRIP_PASSES):
        candidate = unescape(_TAG_PATTERN.sub(" ", text))
        if candidate == text:
            break
        text = candidate
    return normalize_whitespace(_TAG_PATTERN.sub(" ", text))


def _strip_jats(abstract: Any) -> str:
    return _ABSTRACT_LABEL_PATTERN.sub("", _strip_markup(abstract))


def _first_title(item: dict) -> str:
    titles = item.get("title") or []
    for title in titles:
        cleaned = _strip_markup(title)
        if cleaned:
            return cleaned
    return ""


def _author_names(item: dict) -> list[str]:
    names: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        given = _clean_text(author.get("given"))
        family = _clean_text(author.get("family"))
        full = _clean_text(author.get("name")) or " ".join(part for part in (given, family) if part)
        if full:
            names.append(full)
    return names


def _categories(item: dict) -> list[str]:
    seen: list[str] = []
    for subject in item.get("subject") or []:
        cleaned = _clean_text(subject)
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _date_from_parts(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    parts = node.get("date-parts") or []
    if not parts or not isinstance(parts[0], list) or not parts[0]:
        return ""
    values = [int(part) for part in parts[0] if isinstance(part, int)]
    if not values:
        return ""
    year = values[0]
    month = values[1] if len(values) > 1 else 1
    day = values[2] if len(values) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _published_date(item: dict) -> str:
    for key in ("published", "published-online", "published-print", "issued", "created"):
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return ""


def _updated_date(item: dict) -> str:
    for key in ("deposited", "indexed"):
        node = item.get(key)
        if isinstance(node, dict):
            stamp = _clean_text(node.get("date-time"))
            if stamp:
                return stamp[:10]
            value = _date_from_parts(node)
            if value:
                return value
    return _published_date(item)


def _pdf_url(item: dict) -> str:
    for link in item.get("link") or []:
        if not isinstance(link, dict):
            continue
        if _clean_text(link.get("content-type")).lower() == "application/pdf":
            url = _clean_text(link.get("URL"))
            if url:
                return url
    return ""


def _container_title(item: dict) -> str:
    for title in item.get("container-title") or []:
        cleaned = _clean_text(title)
        if cleaned:
            return cleaned
    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list `PaperRecord`.

    Rule da chot (Vai tro 2 quyet dinh, Vai tro 1 uy quyen):
    - `paper_id` = DOI lowercase, la khoa on dinh.
    - Loai record thieu DOI, title hoac abstract.
    - Title/summary bo sach JATS markup truoc khi luu.
    - Deduplicate theo `paper_id`, giu ban dau tien.
    - Sort tang dan theo `paper_id` de snapshot deterministic.

    Raw snapshot giu nguyen record co `published` trong tuong lai (Crossref co
    forthcoming date). Viec loai chung la rule cua cleaning, noi co `run_date`.
    """
    items = ((payload or {}).get("message") or {}).get("items") or []
    records: dict[str, PaperRecord] = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = _clean_text(item.get("DOI")).lower()
        title = _first_title(item)
        summary = _strip_jats(item.get("abstract"))
        if not paper_id or not title or not summary:
            continue
        if paper_id in records:
            continue

        categories = _categories(item)
        work_type = _clean_text(item.get("type"))
        abs_url = _clean_text(item.get("URL")) or f"https://doi.org/{paper_id}"

        records[paper_id] = PaperRecord(
            paper_id=paper_id,
            title=title,
            summary=summary,
            authors=_author_names(item),
            categories=categories,
            primary_category=categories[0] if categories else (work_type or "unknown"),
            published=_published_date(item),
            updated=_updated_date(item),
            abs_url=abs_url,
            pdf_url=_pdf_url(item),
            comment=_container_title(item),
        )

    return [records[key] for key in sorted(records)]


def _build_params(settings: Settings) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "sort": CROSSREF_SORT,
        "order": CROSSREF_ORDER,
    }
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    return params


def _retry_delay(attempt: int, response: requests.Response | None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "").strip()
        if retry_after.isdigit():
            return min(float(retry_after), BACKOFF_CAP_SECONDS)
    return min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_CAP_SECONDS)


def _get_with_retry(url: str, params: dict[str, str | int]) -> dict:
    headers = {"User-Agent": "K4-Day10-Data-Pipeline/1.0 (Crossref REST API client)"}
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response: requests.Response | None = None
        try:
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}"
            if response.status_code not in RETRY_STATUS_CODES:
                raise RuntimeError(f"Crossref request failed with {last_error}.")
        except requests.RequestException as error:
            last_error = f"{type(error).__name__}: {error}"

        if attempt == MAX_ATTEMPTS:
            break
        delay = _retry_delay(attempt, response)
        print(f"[crossref] attempt {attempt}/{MAX_ATTEMPTS} failed ({last_error}); retry in {delay:.1f}s")
        time.sleep(delay)

    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts. Last error: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref, luu raw response va raw records snapshot."""
    payload = _get_with_retry(CROSSREF_API_URL, _build_params(settings))
    write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload)
    if not records:
        raise RuntimeError("Crossref returned no usable record. Blocker: khong freeze baseline rong.")

    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot va map thanh `PaperRecord`. Day la nguon recovery duy nhat."""
    rows = read_json(path)
    if not isinstance(rows, list):
        raise ValueError(f"Raw records snapshot must be a JSON list: {path}")

    records: list[PaperRecord] = []
    for row in rows:
        records.append(
            PaperRecord(
                paper_id=str(row["paper_id"]),
                title=str(row["title"]),
                summary=str(row["summary"]),
                authors=list(row.get("authors") or []),
                categories=list(row.get("categories") or []),
                primary_category=str(row.get("primary_category") or ""),
                published=str(row.get("published") or ""),
                updated=str(row.get("updated") or ""),
                abs_url=str(row.get("abs_url") or ""),
                pdf_url=str(row.get("pdf_url") or ""),
                comment=str(row.get("comment") or ""),
            )
        )
    return records
