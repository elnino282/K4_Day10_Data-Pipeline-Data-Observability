from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json


CROSSREF_API_URL = "https://api.crossref.org/works"
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref response into a stable, source-independent schema.

    Crossref fields are permissive and frequently missing.  This parser keeps
    records that have a DOI, title and abstract, while representing optional
    fields with empty values so downstream code receives a consistent shape.
    """

    def first_text(value: Any) -> str:
        if isinstance(value, list):
            value = value[0] if value else ""
        return normalize_whitespace(str(value or ""))

    def clean_markup(value: Any) -> str:
        text = unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        return normalize_whitespace(text)

    def date_value(item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            candidate = item.get(key)
            if isinstance(candidate, dict):
                parts = candidate.get("date-parts")
                if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                    values = parts[0]
                    year = int(values[0])
                    month = int(values[1]) if len(values) > 1 else 1
                    day = int(values[2]) if len(values) > 2 else 1
                    try:
                        return datetime(year, month, day, tzinfo=UTC).date().isoformat()
                    except ValueError:
                        continue
                timestamp = candidate.get("date-time")
                if timestamp:
                    return str(timestamp)
        return ""

    message = payload.get("message", {})
    items = message.get("items", []) if isinstance(message, dict) else []
    if not isinstance(items, list):
        raise ValueError("Invalid Crossref payload: message.items must be a list.")

    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        paper_id = first_text(item.get("DOI")).lower()
        title = clean_markup(first_text(item.get("title")))
        summary = clean_markup(item.get("abstract"))
        if not paper_id or not title or not summary or paper_id in seen_ids:
            continue

        authors: list[str] = []
        for author in item.get("author", []) or []:
            if not isinstance(author, dict):
                continue
            name = normalize_whitespace(
                " ".join(part for part in (str(author.get("given", "")), str(author.get("family", ""))) if part)
            )
            if name and name not in authors:
                authors.append(name)

        categories = [
            clean_markup(subject)
            for subject in (item.get("subject", []) or [])
            if clean_markup(subject)
        ]
        categories = list(dict.fromkeys(categories))
        published = date_value(item, "published-print", "published-online", "published", "issued", "created")
        updated = date_value(item, "indexed", "deposited", "created")

        pdf_url = ""
        for link in item.get("link", []) or []:
            if not isinstance(link, dict):
                continue
            content_type = str(link.get("content-type", "")).lower()
            url = first_text(link.get("URL"))
            if url and ("pdf" in content_type or url.lower().endswith(".pdf")):
                pdf_url = url
                break

        abs_url = first_text(item.get("URL")) or f"https://doi.org/{paper_id}"
        comment = clean_markup(item.get("subtitle"))
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=categories[0] if categories else "uncategorized",
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )
        seen_ids.add(paper_id)
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref with bounded exponential backoff and persist both raw layers."""
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "select": "DOI,title,abstract,author,subject,published,published-print,published-online,issued,created,indexed,deposited,URL,link,subtitle",
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "day10-data-observability-lab/1.0 (educational RAG pipeline)",
    }
    last_error: Exception | None = None
    response: requests.Response | None = None
    for attempt in range(4):
        try:
            response = requests.get(CROSSREF_API_URL, params=params, headers=headers, timeout=(10, 45))
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                break
            last_error = RuntimeError(f"Crossref returned retryable HTTP {response.status_code}.")
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        if attempt < 3:
            retry_after = response.headers.get("Retry-After") if response is not None else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(min(delay, 8.0))
    else:
        raise RuntimeError(f"Crossref fetch failed after 4 attempts: {last_error}") from last_error

    if response is None:
        raise RuntimeError("Crossref fetch did not produce a response.")
    payload = response.json()
    write_json(settings.paths.raw_api_response, payload)
    records = parse_crossref_payload(payload)
    if not records:
        raise RuntimeError("Crossref returned no usable records with DOI, title and abstract.")
    write_json(settings.paths.raw_records_json, [record.__dict__ for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load and validate the normalized raw-record snapshot."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Raw record snapshot must contain a JSON list: {path}")
    records: list[PaperRecord] = []
    field_names = set(PaperRecord.__dataclass_fields__)
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Raw record {index} is not an object.")
        missing = field_names - set(item)
        if missing:
            raise ValueError(f"Raw record {index} is missing fields: {sorted(missing)}")
        values = {name: item[name] for name in field_names}
        values["authors"] = list(values["authors"] or [])
        values["categories"] = list(values["categories"] or [])
        records.append(PaperRecord(**values))
    return records
