from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import hashlib
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import file_sha256, write_json
from ingestion.cleaning import CLEAN_COLUMNS, NORMALIZE_RULES
from ingestion.crossref import CROSSREF_API_URL

MANIFEST_FILENAME = "baseline_manifest.json"

RECOVERY_CRITERIA = [
    "schema giong baseline",
    "row count giong baseline",
    "tap paper_id giong baseline",
    "noi dung canonical tung record giong baseline",
    "danh gia tren cung test set",
]

CSV_READ_CONVENTION = (
    "Doc CSV bang pd.read_csv(path, keep_default_na=False). Cot rong (`categories_joined`, "
    "`pdf_url`) se thanh NaN float neu doc mac dinh, pha contract kieu chuoi. "
    "papers_clean.json khong dinh van de nay."
)


def sha256_paper_ids(paper_ids: list[str]) -> str:
    """Hash tap paper_id theo thu tu da sort, moi id mot dong."""
    return hashlib.sha256("\n".join(paper_ids).encode("utf-8")).hexdigest()


def _relative_path(path: Path, project_dir: Path) -> str:
    """Path tuong doi theo repo, dung dau `/`: manifest phai giong nhau tren moi may."""
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _artifact_entry(path: Path, project_dir: Path) -> dict[str, Any]:
    relative = _relative_path(path, project_dir)
    if not path.exists():
        return {"path": relative, "present": False}
    return {
        "path": relative,
        "present": True,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def build_baseline_manifest(
    settings: Settings, df: pd.DataFrame, run_date: datetime | date
) -> dict[str, Any]:
    """Provenance cua baseline freeze.

    Khong chua wall-clock timestamp: manifest phai deterministic de doi chieu
    truc tiep voi manifest cua repaired artifact.
    """
    run_day = run_date.date() if isinstance(run_date, datetime) else run_date
    paper_ids = df["paper_id"].tolist()
    paths = settings.paths

    return {
        "run_date": run_day.isoformat(),
        "source": {
            "api": settings.source_api,
            "endpoint": CROSSREF_API_URL,
            "query": settings.source_query,
            "filter": settings.source_filter,
            "rows": settings.max_results,
            "sort": "relevance (mac dinh cua Crossref khi co query, khong gui tham so sort)",
        },
        "clean_contract": {
            "columns": CLEAN_COLUMNS,
            "key": "paper_id",
            "normalize_rules": NORMALIZE_RULES,
            "csv_read_convention": CSV_READ_CONVENTION,
        },
        "counts": {
            "clean_rows": int(len(df)),
            "unique_paper_id": int(df["paper_id"].nunique()),
        },
        "paper_id_sha256": sha256_paper_ids(paper_ids),
        "paper_ids": paper_ids,
        "column_empty_counts": {
            column: int((df[column].astype("string").fillna("") == "").sum())
            for column in CLEAN_COLUMNS
            if column not in {"age_days", "summary_chars"}
        },
        "ranges": {
            "age_days": [int(df["age_days"].min()), int(df["age_days"].max())],
            "summary_chars": [int(df["summary_chars"].min()), int(df["summary_chars"].max())],
            "published": [df["published"].min(), df["published"].max()],
        },
        "artifacts": {
            "raw_api_response": _artifact_entry(paths.raw_api_response, paths.project_dir),
            "raw_request_metadata": _artifact_entry(paths.raw_request_metadata, paths.project_dir),
            "raw_records_json": _artifact_entry(paths.raw_records_json, paths.project_dir),
            "clean_csv": _artifact_entry(paths.clean_csv, paths.project_dir),
            "clean_json": _artifact_entry(paths.clean_json, paths.project_dir),
        },
        "cleaning_trace": df.attrs.get("cleaning_trace", {}),
        "recovery": {
            "source_of_truth": _relative_path(paths.raw_records_json, paths.project_dir),
            "criteria": RECOVERY_CRITERIA,
            "note": "Repaired phai rerun cleaning voi dung run_date nay. Metric recovery mot minh khong du.",
        },
    }


def manifest_path(settings: Settings) -> Path:
    return settings.paths.clean_csv.parent / MANIFEST_FILENAME


def write_baseline_manifest(
    settings: Settings, df: pd.DataFrame, run_date: datetime | date
) -> Path:
    path = manifest_path(settings)
    write_json(path, build_baseline_manifest(settings, df, run_date))
    return path
