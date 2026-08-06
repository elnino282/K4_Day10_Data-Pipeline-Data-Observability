from __future__ import annotations

from datetime import UTC, datetime, date
from html import unescape
import re
from typing import Any
import unicodedata

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "authors_joined",
    "categories",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "summary_chars",
    "abs_url",
    "pdf_url",
    "comment",
    "text_for_embedding",
]

NORMALIZE_RULES = [
    "paper_id: strip + lowercase",
    "title/summary: normalize_whitespace",
    "authors/categories: join bang ', ', bo phan tu rong",
    "published: bat buoc dinh dang YYYY-MM-DD",
    "text_for_embedding: ghep section khong rong theo thu tu co dinh",
]

MIN_SUMMARY_CHARS = 40


def _build_text_for_embedding(
    title: str, authors_joined: str, categories_joined: str, published: str, summary: str
) -> str:
    """Ghep deterministic tu noi dung canonical. Section rong bi bo qua."""
    sections = [
        ("Title", title),
        ("Authors", authors_joined),
        ("Categories", categories_joined),
        ("Published", published),
        ("Summary", summary),
    ]
    return "\n".join(f"{label}: {value}" for label, value in sections if value)


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize source records into the canonical dataframe used by every phase."""

    def clean_text(value: object) -> str:
        text = unicodedata.normalize("NFKC", unescape(str(value or "")))
        text = re.sub(r"<[^>]+>", " ", text)
        return normalize_whitespace(text)

    def clean_list(values: list[str]) -> list[str]:
        normalized = [clean_text(value) for value in (values or [])]
        return list(dict.fromkeys(value for value in normalized if value))

    run_timestamp = pd.Timestamp(run_date)
    if run_timestamp.tzinfo is None:
        run_timestamp = run_timestamp.tz_localize(UTC)
    else:
        run_timestamp = run_timestamp.tz_convert(UTC)
    run_day = run_timestamp.date()

    rows: list[dict[str, object]] = []
    dropped: list[dict[str, str]] = []
    duplicate_keys: list[str] = []
    seen: set[str] = set()

    for record in records:
        paper_id = clean_text(record.paper_id).lower()
        title = clean_text(record.title)
        summary = clean_text(record.summary)

        if not paper_id:
            dropped.append({"paper_id": "", "reason": "missing_paper_id"})
            continue
        if len(title) < 5:
            dropped.append({"paper_id": paper_id, "reason": "missing_title"})
            continue
        if len(summary) < MIN_SUMMARY_CHARS:
            dropped.append({"paper_id": paper_id, "reason": "missing_summary"})
            continue

        published_ts = pd.to_datetime(record.published, errors="coerce", utc=True)
        if pd.isna(published_ts):
            dropped.append({"paper_id": paper_id, "reason": "unparsable_published"})
            continue

        published_date = published_ts.date()
        if published_date > run_day:
            dropped.append({"paper_id": paper_id, "reason": "published_after_run_date"})
            continue

        if paper_id in seen:
            duplicate_keys.append(paper_id)
            dropped.append({"paper_id": paper_id, "reason": "duplicate_paper_id"})
            continue
        seen.add(paper_id)

        updated_ts = pd.to_datetime(record.updated, errors="coerce", utc=True)
        authors = clean_list(record.authors)
        categories = clean_list(record.categories)
        authors_joined = compact_join(authors)
        categories_joined = compact_join(categories)
        primary_category = clean_text(record.primary_category) or (categories[0] if categories else "uncategorized")
        published = published_date.isoformat()
        updated = "" if pd.isna(updated_ts) else updated_ts.isoformat().replace("+00:00", "Z")
        age_days = int((run_timestamp.normalize() - published_ts.normalize()).days)

        text_for_embedding = normalize_whitespace(
            f"Title: {title}. Abstract: {summary} Authors: {authors_joined or 'Unknown'}. "
            f"Topics: {categories_joined or primary_category}. Published: {published}."
        )

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "authors_joined": authors_joined,
                "categories": categories,
                "categories_joined": categories_joined,
                "primary_category": primary_category,
                "published": published,
                "updated": updated,
                "age_days": age_days,
                "summary_chars": len(summary),
                "abs_url": clean_text(record.abs_url),
                "pdf_url": clean_text(record.pdf_url),
                "comment": clean_text(record.comment),
                "text_for_embedding": text_for_embedding,
            }
        )

    if not rows:
        df = pd.DataFrame(columns=CLEAN_COLUMNS)
    else:
        df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
        df = df.drop_duplicates(subset=["paper_id"], keep="first")
        df = df.sort_values(["published", "paper_id"], ascending=[False, True], kind="stable").reset_index(drop=True)

    df["age_days"] = df["age_days"].astype("int64") if not df.empty else pd.Series(dtype="int64")
    df["summary_chars"] = df["summary_chars"].astype("int64") if not df.empty else pd.Series(dtype="int64")

    df.attrs["cleaning_trace"] = {
        "run_date": run_day.isoformat(),
        "records_in": len(records),
        "records_out": int(len(df)),
        "dropped_count": len(dropped),
        "dropped": dropped,
        "duplicate_keys": duplicate_keys,
        "normalize_rules": NORMALIZE_RULES,
    }
    return df

