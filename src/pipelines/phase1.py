from __future__ import annotations

import json

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


INDEX_REQUIRED_COLUMNS = {
    "age_days",
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
}


def _validate_clean_dataframe(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("Cleaning produced an empty dataset; baseline cannot continue.")
    missing_columns = sorted(INDEX_REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataset is missing required columns: {', '.join(missing_columns)}")


def _dataframe_records(df: pd.DataFrame) -> list[dict]:
    """Convert a dataframe to JSON-safe records, including datetime columns."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


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

    clean_df = build_clean_dataframe(records, run_date=now_utc())
    _validate_clean_dataframe(clean_df)
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings=settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    should_build_test_set = settings.refresh_test_set or not settings.paths.eval_testset.exists()
    if should_build_test_set:
        test_set = build_test_set(clean_df, settings.paths.eval_testset)
    else:
        test_set = read_json(settings.paths.eval_testset)
    if not isinstance(test_set, list) or not test_set:
        raise ValueError("Evaluation test set is empty or invalid; baseline cannot continue.")

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    quality = run_data_quality_checks(clean_df, settings=settings, report_name="baseline")
    freshness = build_freshness_report(
        clean_df,
        settings=settings,
        report_path=settings.paths.freshness_report,
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
        "used_cached_snapshot": use_cached_source,
    }
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )

    print(f"Baseline pipeline completed with {len(clean_df)} clean records.")
    print(f"Metrics: {settings.paths.baseline_metrics}")
    print(f"Report: {settings.paths.baseline_report}")
