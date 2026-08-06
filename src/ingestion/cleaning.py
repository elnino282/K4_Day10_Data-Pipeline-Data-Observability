from __future__ import annotations

from datetime import UTC, datetime
from html import unescape
import unicodedata

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord, strip_markup


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
    "text: NFKC + unescape + strip markup (giu lai toan tu so sanh nhu 'p < 0.001')",
    "paper_id: strip + lowercase",
    "authors/categories: clean tung phan tu, bo rong, bo trung lap theo thu tu",
    "loai record neu title < 5 ky tu, summary < 40 ky tu hoac published khong parse duoc",
    "deduplicate theo paper_id (giu ban dau tien), sort published giam dan roi paper_id tang dan",
]


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize source records into the canonical dataframe used by every phase.

    Trace cua lan clean nay nam o `df.attrs["cleaning_trace"]`: record vao/ra,
    record bi loai kem ly do, duplicate key va rule normalize. `attrs` khong ton
    tai qua `to_csv`/`to_json`, nen consumer phai doc truoc khi ghi file.
    """

    def clean_text(value: object) -> str:
        text = unicodedata.normalize("NFKC", unescape(str(value or "")))
        return strip_markup(text)

    def clean_list(values: list[str]) -> list[str]:
        normalized = [clean_text(value) for value in (values or [])]
        return list(dict.fromkeys(value for value in normalized if value))

    run_timestamp = pd.Timestamp(run_date)
    if run_timestamp.tzinfo is None:
        run_timestamp = run_timestamp.tz_localize(UTC)
    else:
        run_timestamp = run_timestamp.tz_convert(UTC)

    rows: list[dict[str, object]] = []
    dropped: list[dict[str, str]] = []
    for record in records:
        paper_id = clean_text(record.paper_id).lower()
        title = clean_text(record.title)
        summary = clean_text(record.summary)
        if not paper_id:
            dropped.append({"paper_id": "", "reason": "missing_paper_id"})
            continue
        if len(title) < 5:
            dropped.append({"paper_id": paper_id, "reason": "title_too_short"})
            continue
        if len(summary) < 40:
            dropped.append({"paper_id": paper_id, "reason": "summary_too_short"})
            continue

        published_ts = pd.to_datetime(record.published, errors="coerce", utc=True)
        if pd.isna(published_ts):
            dropped.append({"paper_id": paper_id, "reason": "unparsable_published"})
            continue
        updated_ts = pd.to_datetime(record.updated, errors="coerce", utc=True)
        authors = clean_list(record.authors)
        categories = clean_list(record.categories)
        authors_joined = compact_join(authors)
        categories_joined = compact_join(categories)
        primary_category = clean_text(record.primary_category) or (categories[0] if categories else "uncategorized")
        published = published_ts.date().isoformat()
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

    def with_trace(frame: pd.DataFrame, duplicate_keys: list[str]) -> pd.DataFrame:
        frame.attrs["cleaning_trace"] = {
            "run_date": run_timestamp.date().isoformat(),
            "records_in": len(records),
            "records_out": int(len(frame)),
            "dropped_count": len(dropped) + len(duplicate_keys),
            "dropped": dropped
            + [{"paper_id": key, "reason": "duplicate_paper_id"} for key in duplicate_keys],
            "duplicate_keys": duplicate_keys,
            "normalize_rules": NORMALIZE_RULES,
        }
        return frame

    if not rows:
        return with_trace(pd.DataFrame(columns=CLEAN_COLUMNS), [])
    result = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    duplicate_keys = result.loc[result["paper_id"].duplicated(keep="first"), "paper_id"].tolist()
    result = result.drop_duplicates(subset=["paper_id"], keep="first")
    result = result.sort_values(["published", "paper_id"], ascending=[False, True], kind="stable")
    return with_trace(result.reset_index(drop=True), duplicate_keys)
