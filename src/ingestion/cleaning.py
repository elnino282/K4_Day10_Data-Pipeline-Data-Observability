from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
    "abs_url",
    "pdf_url",
    "text_for_embedding",
    "age_days",
    "summary_chars",
]

NORMALIZE_RULES = [
    "paper_id: strip + lowercase",
    "title/summary: normalize_whitespace",
    "authors/categories: join bang ', ', bo phan tu rong",
    "published: bat buoc dinh dang YYYY-MM-DD",
    "text_for_embedding: ghep section khong rong theo thu tu co dinh",
]

MIN_SUMMARY_CHARS = 1


def _parse_published(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (AttributeError, ValueError):
        return None


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
    """Clean raw records thanh dataframe san sang de embed.

    Rule da chot (Vai tro 2):
    - Loai record thieu `paper_id`, `title`, `summary` hoac `published` khong parse duoc.
    - Loai record co `published` sau `run_date`: Crossref co forthcoming date,
      giu lai se lam `age_days` am va pha freshness report.
    - Deduplicate theo `paper_id`, giu ban dau tien; sort tang dan theo `paper_id`.
    - `age_days` = so ngay tu `published` den `run_date`.

    Trace cua lan clean nay nam o `df.attrs["cleaning_trace"]`: record vao/ra,
    record bi loai kem ly do, duplicate key va rule normalize.
    """
    run_day = run_date.date() if isinstance(run_date, datetime) else run_date

    rows: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    duplicate_keys: list[str] = []
    seen: set[str] = set()

    for record in records:
        paper_id = normalize_whitespace(record.paper_id).lower()
        title = normalize_whitespace(record.title)
        summary = normalize_whitespace(record.summary)

        if not paper_id:
            dropped.append({"paper_id": "", "reason": "missing_paper_id"})
            continue
        if not title:
            dropped.append({"paper_id": paper_id, "reason": "missing_title"})
            continue
        if len(summary) < MIN_SUMMARY_CHARS:
            dropped.append({"paper_id": paper_id, "reason": "missing_summary"})
            continue

        published_date = _parse_published(record.published)
        if published_date is None:
            dropped.append({"paper_id": paper_id, "reason": "unparsable_published"})
            continue
        if published_date > run_day:
            dropped.append({"paper_id": paper_id, "reason": "published_after_run_date"})
            continue

        if paper_id in seen:
            duplicate_keys.append(paper_id)
            dropped.append({"paper_id": paper_id, "reason": "duplicate_paper_id"})
            continue
        seen.add(paper_id)

        published = published_date.isoformat()
        authors_joined = compact_join(normalize_whitespace(author) for author in record.authors)
        categories_joined = compact_join(normalize_whitespace(item) for item in record.categories)

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "published": published,
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "abs_url": normalize_whitespace(record.abs_url),
                "pdf_url": normalize_whitespace(record.pdf_url),
                "text_for_embedding": _build_text_for_embedding(
                    title, authors_joined, categories_joined, published, summary
                ),
                "age_days": (run_day - published_date).days,
                "summary_chars": len(summary),
            }
        )

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    df = df.sort_values("paper_id", kind="stable").reset_index(drop=True)
    df["age_days"] = df["age_days"].astype("int64")
    df["summary_chars"] = df["summary_chars"].astype("int64")

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
