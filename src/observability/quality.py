from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json


MIN_SUMMARY_CHARS = 80


def _text_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    return df[column].fillna("").astype(str).str.strip()


def _check(name: str, observed: Any, expectation: str, passed: bool, details: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "observed": observed,
        "expectation": expectation,
        "passed": bool(passed),
    }
    if details is not None:
        payload["details"] = details
    return payload


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run dataframe quality checks and write a state-specific JSON artifact."""
    total_rows = int(len(df))
    paper_ids = _text_series(df, "paper_id")
    titles = _text_series(df, "title")
    summaries = _text_series(df, "summary")

    missing_columns = sorted(
        {
            "paper_id",
            "title",
            "summary",
            "published",
            "age_days",
            "text_for_embedding",
        }
        - set(df.columns)
    )
    null_paper_ids = int((paper_ids == "").sum())
    duplicate_paper_ids = int(paper_ids[paper_ids != ""].duplicated().sum())
    empty_titles = int((titles == "").sum())
    empty_summaries = int((summaries == "").sum())
    short_summaries = int(((summaries != "") & (summaries.str.len() < MIN_SUMMARY_CHARS)).sum())
    duplicate_rows = int(df.duplicated().sum()) if total_rows else 0

    if "age_days" in df.columns:
        age_values = pd.to_numeric(df["age_days"], errors="coerce")
        missing_age_days = int(age_values.isna().sum())
        negative_age_days = int((age_values < 0).sum())
        stale_rows = int((age_values > settings.freshness_threshold_days).sum())
    else:
        age_values = pd.Series([], dtype="float64")
        missing_age_days = total_rows
        negative_age_days = 0
        stale_rows = 0

    checks = [
        _check("required_columns_present", missing_columns, "no missing required columns", not missing_columns),
        _check("row_count", total_rows, "row count > 0", total_rows > 0),
        _check("paper_id_not_null", null_paper_ids, "0 blank/null paper_id values", null_paper_ids == 0),
        _check("paper_id_unique", duplicate_paper_ids, "0 duplicate paper_id values", duplicate_paper_ids == 0),
        _check("title_not_empty", empty_titles, "0 blank/null title values", empty_titles == 0),
        _check("summary_not_empty", empty_summaries, "0 blank/null summary values", empty_summaries == 0),
        _check(
            "summary_min_length",
            short_summaries,
            f"0 non-empty summaries shorter than {MIN_SUMMARY_CHARS} chars",
            short_summaries == 0,
        ),
        _check("duplicate_rows", duplicate_rows, "0 exact duplicate rows", duplicate_rows == 0),
        _check("age_days_present", missing_age_days, "0 missing/non-numeric age_days values", missing_age_days == 0),
        _check("age_days_non_negative", negative_age_days, "0 negative age_days values", negative_age_days == 0),
        _check(
            "freshness_threshold",
            stale_rows,
            f"0 rows older than {settings.freshness_threshold_days} days",
            stale_rows == 0,
        ),
    ]

    payload = {
        "state": report_name,
        "measured_at_utc": now_utc().isoformat(),
        "input_rows": total_rows,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "summary": {
            "missing_columns": missing_columns,
            "null_paper_ids": null_paper_ids,
            "duplicate_paper_ids": duplicate_paper_ids,
            "empty_titles": empty_titles,
            "empty_summaries": empty_summaries,
            "short_summaries": short_summaries,
            "duplicate_rows": duplicate_rows,
            "missing_age_days": missing_age_days,
            "negative_age_days": negative_age_days,
            "stale_rows": stale_rows,
        },
    }
    report_path = settings.paths.quality_dir / f"{report_name}_quality.json"
    write_json(report_path, payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build and write a freshness report from published dates and age_days."""
    total_rows = int(len(df))
    published = pd.to_datetime(df["published"], errors="coerce") if "published" in df.columns else pd.Series([])
    invalid_published = int(published.isna().sum()) if total_rows else 0

    if "age_days" in df.columns:
        age_days = pd.to_numeric(df["age_days"], errors="coerce")
        stale_rows = int((age_days > settings.freshness_threshold_days).sum())
        missing_age_days = int(age_days.isna().sum())
    else:
        stale_rows = 0
        missing_age_days = total_rows

    latest = published.max() if total_rows and not published.dropna().empty else None
    oldest = published.min() if total_rows and not published.dropna().empty else None

    status = "fresh"
    if total_rows == 0 or invalid_published == total_rows:
        status = "unknown"
    elif stale_rows > 0 or missing_age_days > 0 or invalid_published > 0:
        status = "stale"

    payload = {
        "measured_at_utc": now_utc().isoformat(),
        "latest_published": latest.date().isoformat() if latest is not None else None,
        "oldest_published": oldest.date().isoformat() if oldest is not None else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "invalid_published": invalid_published,
        "missing_age_days": missing_age_days,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "status": status,
        "is_fresh": status == "fresh",
    }
    write_json(Path(report_path), payload)
    return payload
