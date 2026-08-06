from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_SUMMARY_CHARS = 40


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run schema, completeness, uniqueness, validity and freshness checks."""
    required_columns = {
        "paper_id",
        "title",
        "summary",
        "published",
        "age_days",
        "summary_chars",
        "text_for_embedding",
    }
    checks: list[dict[str, Any]] = []

    def add(name: str, success: bool, observed: Any, expectation: str, dimension: str) -> None:
        checks.append(
            {
                "name": name,
                "dimension": dimension,
                "success": bool(success),
                "passed": bool(success),
                "observed": observed,
                "expectation": expectation,
            }
        )

    missing = sorted(required_columns - set(df.columns))
    add("required_columns", not missing, missing, "no required columns are missing", "schema")
    add("minimum_row_count", len(df) >= 4, int(len(df)), ">= 4 rows", "volume")

    if not missing and len(df):
        ids = df["paper_id"].fillna("").astype(str).str.strip()
        titles = df["title"].fillna("").astype(str).str.strip()
        summaries = df["summary"].fillna("").astype(str).str.strip()
        embedded = df["text_for_embedding"].fillna("").astype(str).str.strip()
        ages = pd.to_numeric(df["age_days"], errors="coerce")
        published = pd.to_datetime(df["published"], errors="coerce", utc=True)
        summary_chars = pd.to_numeric(df["summary_chars"], errors="coerce")

        add("paper_id_complete", bool(ids.ne("").all()), int(ids.eq("").sum()), "0 blank IDs", "completeness")
        duplicate_count = int(ids.duplicated(keep=False).sum())
        add("paper_id_unique", duplicate_count == 0, duplicate_count, "0 rows with duplicate IDs", "uniqueness")
        add("title_complete", bool(titles.ne("").all()), int(titles.eq("").sum()), "0 blank titles", "completeness")
        short_title_rate = float(titles.str.len().lt(8).mean())
        add("title_length", short_title_rate <= 0.05, round(short_title_rate, 4), "<= 5% titles shorter than 8 chars", "validity")
        blank_summary_rate = float(summaries.eq("").mean())
        add("summary_complete", blank_summary_rate <= 0.05, round(blank_summary_rate, 4), "<= 5% blank summaries", "completeness")
        short_summary_rate = float(summaries.str.len().lt(40).mean())
        add("summary_length", short_summary_rate <= 0.10, round(short_summary_rate, 4), "<= 10% summaries shorter than 40 chars", "validity")
        add("published_valid", bool(published.notna().all()), int(published.isna().sum()), "0 invalid dates", "validity")
        invalid_age_rate = float((ages.isna() | ages.lt(-30)).mean())
        add("age_days_valid", invalid_age_rate <= 0.05, round(invalid_age_rate, 4), "<= 5% invalid ages", "validity")
        stale_rate = float(ages.gt(settings.freshness_threshold_days).mean())
        add("freshness_ratio", stale_rate <= 0.20, round(stale_rate, 4), "<= 20% stale rows", "freshness")
        embedding_blank_rate = float(embedded.eq("").mean())
        add("embedding_text_complete", embedding_blank_rate == 0.0, round(embedding_blank_rate, 4), "0 blank embedding texts", "completeness")
        inconsistent_chars = int((summary_chars.fillna(-1).astype(int) != summaries.str.len()).sum())
        add("summary_chars_consistent", inconsistent_chars == 0, inconsistent_chars, "0 inconsistent rows", "consistency")

    successful = sum(1 for check in checks if check["success"])
    overall_success = successful == len(checks)
    payload = {
        "report_name": report_name,
        "state": report_name,
        "measured_at_utc": now_utc().isoformat(),
        "framework": "declarative_quality_checks",
        "overall_success": overall_success,
        "passed": overall_success,
        "statistics": {
            "evaluated_checks": len(checks),
            "successful_checks": successful,
            "unsuccessful_checks": len(checks) - successful,
            "success_percent": round(100.0 * successful / len(checks), 2) if checks else 0.0,
        },
        "row_count": int(len(df)),
        "input_rows": int(len(df)),
        "freshness_threshold_days": settings.freshness_threshold_days,
        "checks": checks,
    }
    settings.paths.quality_dir.mkdir(parents=True, exist_ok=True)
    write_json(settings.paths.quality_dir / f"{report_name}_quality.json", payload)
    write_json(settings.paths.quality_dir / f"{report_name}.json", payload)
    if hasattr(settings.paths, "gx_dir"):
        settings.paths.gx_dir.mkdir(parents=True, exist_ok=True)
        write_json(settings.paths.gx_dir / f"{report_name}.json", payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path: str | Path) -> dict[str, Any]:
    """Summarize publication recency with an explicit service-level threshold."""
    published = pd.to_datetime(df.get("published", pd.Series(dtype=str)), errors="coerce", utc=True)
    ages = pd.to_numeric(df.get("age_days", pd.Series(dtype=float)), errors="coerce")
    stale_mask = ages.gt(settings.freshness_threshold_days)
    total_rows = int(len(df))
    stale_rows = int(stale_mask.sum())
    valid_dates = published.dropna()
    is_fresh = bool(total_rows and stale_rows == 0 and published.notna().all())
    payload = {
        "measured_at_utc": now_utc().isoformat(),
        "threshold_days": settings.freshness_threshold_days,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "latest_published": valid_dates.max().date().isoformat() if not valid_dates.empty else None,
        "oldest_published": valid_dates.min().date().isoformat() if not valid_dates.empty else None,
        "stale_rows": stale_rows,
        "fresh_rows": max(0, total_rows - stale_rows),
        "total_rows": total_rows,
        "stale_ratio": round(stale_rows / total_rows, 4) if total_rows else 1.0,
        "invalid_date_rows": int(published.isna().sum()),
        "invalid_published": int(published.isna().sum()),
        "is_fresh": is_fresh,
        "status": "fresh" if is_fresh else "stale_or_invalid",
    }
    write_json(Path(report_path), payload)
    return payload

