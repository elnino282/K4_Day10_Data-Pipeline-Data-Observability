from __future__ import annotations

import json
import math

import pandas as pd

from core.config import load_settings
from core.utils import (
    ArtifactValidationError,
    file_sha256,
    now_utc,
    read_json,
    require_file_artifact,
    require_json_artifact,
    write_csv,
    write_json,
)
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


CLEAN_REQUIRED_COLUMNS = {
    "age_days",
    "abs_url",
    "authors_joined",
    "categories_joined",
    "paper_id",
    "pdf_url",
    "published",
    "summary",
    "summary_chars",
    "title",
    "text_for_embedding",
}


def _validate_clean_dataframe(df: pd.DataFrame) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Cleaning must return a pandas DataFrame.")
    if df.empty:
        raise ValueError("Cleaning produced an empty dataset; baseline cannot continue.")
    missing_columns = sorted(CLEAN_REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataset is missing required columns: {', '.join(missing_columns)}")

    normalized_ids = df["paper_id"].fillna("").astype(str).str.strip().str.lower()
    if normalized_ids.eq("").any():
        raise ValueError("Clean dataset contains null or blank paper_id values.")
    duplicate_ids = sorted(normalized_ids[normalized_ids.duplicated(keep=False)].unique())
    if duplicate_ids:
        preview = ", ".join(duplicate_ids[:5])
        raise ValueError(f"Clean dataset contains duplicate paper_id values: {preview}")

    for column in ("title", "summary", "text_for_embedding"):
        blank_rows = df[column].fillna("").astype(str).str.strip().eq("")
        if blank_rows.any():
            raise ValueError(f"Clean dataset contains {int(blank_rows.sum())} blank {column} values.")

    published = pd.to_datetime(df["published"], errors="coerce")
    if published.isna().any():
        raise ValueError(
            f"Clean dataset contains {int(published.isna().sum())} invalid published values."
        )

    age_days = pd.to_numeric(df["age_days"], errors="coerce")
    finite_age = age_days.map(lambda value: math.isfinite(float(value)) if pd.notna(value) else False)
    invalid_age = ~finite_age | (age_days < 0)
    if invalid_age.any():
        raise ValueError(
            f"Clean dataset contains {int(invalid_age.sum())} invalid age_days values."
        )

    summary_chars = pd.to_numeric(df["summary_chars"], errors="coerce")
    expected_summary_chars = df["summary"].astype(str).str.len()
    finite_summary_chars = summary_chars.map(
        lambda value: math.isfinite(float(value)) if pd.notna(value) else False
    )
    invalid_summary_chars = (
        ~finite_summary_chars
        | (summary_chars < 0)
        | summary_chars.ne(expected_summary_chars)
    )
    if invalid_summary_chars.any():
        raise ValueError(
            "Clean dataset summary_chars does not match the cleaned summary length "
            f"for {int(invalid_summary_chars.sum())} rows."
        )


def _dataframe_records(df: pd.DataFrame) -> list[dict]:
    """Convert a dataframe to JSON-safe records, including datetime columns."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _validate_clean_artifacts(df: pd.DataFrame, csv_path, json_path) -> None:
    require_file_artifact(csv_path, "baseline clean CSV")
    json_records = require_json_artifact(json_path, "baseline clean JSON", list)
    try:
        csv_records = pd.read_csv(csv_path)
    except Exception as exc:
        raise ArtifactValidationError(f"Baseline clean CSV cannot be read: {csv_path}") from exc
    if len(csv_records) != len(df) or len(json_records) != len(df):
        raise ArtifactValidationError(
            "Baseline clean artifacts do not match the in-memory row count: "
            f"dataframe={len(df)}, csv={len(csv_records)}, json={len(json_records)}."
        )
    expected_columns = set(df.columns)
    json_columns = set().union(*(record.keys() for record in json_records)) if json_records else set()
    if set(csv_records.columns) != expected_columns or json_columns != expected_columns:
        raise ArtifactValidationError(
            "Baseline clean CSV/JSON schema does not match the accepted clean dataframe."
        )

    expected_ids = set(df["paper_id"].astype(str).str.strip().str.lower())
    csv_ids = set(csv_records["paper_id"].astype(str).str.strip().str.lower())
    json_ids = {
        str(record.get("paper_id", "")).strip().lower()
        for record in json_records
    }
    if csv_ids != expected_ids or json_ids != expected_ids:
        raise ArtifactValidationError(
            "Baseline clean CSV/JSON paper_id sets do not match the accepted clean dataframe."
        )


def main() -> None:
    """Run the clean-data baseline from source snapshot through reporting."""
    settings = load_settings()
    raw_snapshot_complete = all(
        path.exists()
        for path in (
            settings.paths.raw_api_response,
            settings.paths.raw_request_metadata,
            settings.paths.raw_records_json,
        )
    )
    use_cached_source = raw_snapshot_complete and not settings.refresh_source

    if use_cached_source:
        records = load_raw_records(settings.paths.raw_records_json)
    else:
        records = fetch_source_records(settings)
    if not records:
        raise ValueError("Source ingestion produced no records; baseline cannot continue.")
    require_json_artifact(settings.paths.raw_api_response, "raw Crossref response", dict)
    require_json_artifact(settings.paths.raw_request_metadata, "raw request metadata", dict)
    raw_record_payload = require_json_artifact(
        settings.paths.raw_records_json,
        "raw parsed records",
        list,
    )
    if len(raw_record_payload) != len(records):
        raise ArtifactValidationError(
            "Loaded source records do not match the raw snapshot count: "
            f"loaded={len(records)}, snapshot={len(raw_record_payload)}."
        )
    loaded_ids = {str(getattr(record, "paper_id", "")).strip().lower() for record in records}
    snapshot_ids = {
        str(record.get("paper_id", "")).strip().lower()
        for record in raw_record_payload
        if isinstance(record, dict)
    }
    if loaded_ids != snapshot_ids:
        raise ArtifactValidationError(
            "Loaded source paper_id set does not match the raw records snapshot."
        )

    clean_df = build_clean_dataframe(records, run_date=now_utc())
    _validate_clean_dataframe(clean_df)
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))
    _validate_clean_artifacts(clean_df, settings.paths.clean_csv, settings.paths.clean_json)

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings=settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )
    require_json_artifact(settings.paths.embeddings_json, "baseline embedding manifest", dict)

    should_build_test_set = settings.refresh_test_set or not settings.paths.eval_testset.exists()
    if should_build_test_set:
        build_test_set(clean_df, settings.paths.eval_testset)
    test_set = require_json_artifact(settings.paths.eval_testset, "evaluation test set", list)
    if not isinstance(test_set, list) or not test_set:
        raise ValueError("Evaluation test set is empty or invalid; baseline cannot continue.")

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    metrics_payload = require_json_artifact(
        settings.paths.baseline_metrics,
        "baseline metrics",
        dict,
    )
    require_json_artifact(settings.paths.baseline_answers, "baseline answers", list)
    if metrics_payload != evaluation.summary:
        raise ArtifactValidationError(
            "Baseline metrics artifact does not match the evaluation summary returned in memory."
        )
    quality = run_data_quality_checks(clean_df, settings=settings, report_name="baseline")
    quality_payload = require_json_artifact(
        settings.paths.baseline_quality_report,
        "baseline quality report",
        dict,
    )
    if quality_payload != quality:
        raise ArtifactValidationError(
            "Baseline quality artifact does not match the quality result returned in memory."
        )
    freshness = build_freshness_report(
        clean_df,
        settings=settings,
        report_path=settings.paths.baseline_freshness_report,
    )
    freshness_payload = require_json_artifact(
        settings.paths.baseline_freshness_report,
        "baseline freshness report",
        dict,
    )
    if freshness_payload != freshness:
        raise ArtifactValidationError(
            "Baseline freshness artifact does not match the freshness result returned in memory."
        )

    request_metadata = (
        read_json(settings.paths.raw_request_metadata)
        if settings.paths.raw_request_metadata.exists()
        else {}
    )
    request_params = request_metadata.get("request", {}) if isinstance(request_metadata, dict) else {}
    source_summary = {
        "source": request_metadata.get("source", settings.source_api),
        "query": request_params.get("query", settings.source_query),
        "filter": request_params.get("filter", settings.source_filter),
        "requested_records": request_params.get("rows", settings.max_results),
        "parsed_records": len(records),
        "clean_records": len(clean_df),
        "fetched_at_utc": request_metadata.get("fetched_at_utc"),
        "raw_response_path": str(settings.paths.raw_api_response),
        "raw_request_metadata_path": str(settings.paths.raw_request_metadata),
        "raw_records_path": str(settings.paths.raw_records_json),
        "raw_response_sha256": file_sha256(settings.paths.raw_api_response),
        "raw_records_sha256": file_sha256(settings.paths.raw_records_json),
        "test_set_sha256": file_sha256(settings.paths.eval_testset),
        "used_cached_snapshot": use_cached_source,
    }
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )
    require_file_artifact(settings.paths.baseline_report, "phase 1 Markdown report")

    print(f"Baseline pipeline completed with {len(clean_df)} clean records.")
    print(f"Metrics: {settings.paths.baseline_metrics}")
    print(f"Report: {settings.paths.baseline_report}")
