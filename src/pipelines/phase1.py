from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import CROSSREF_API_URL, fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex


def _dataframe_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", force_ascii=False))


def _load_or_fetch_records(settings):
    snapshot = settings.paths.raw_records_json
    if not settings.refresh_source and snapshot.exists():
        return load_raw_records(snapshot), "normalized raw snapshot"
    try:
        return fetch_source_records(settings), "live Crossref API"
    except Exception:
        if snapshot.exists():
            return load_raw_records(snapshot), "normalized raw snapshot (live refresh failed)"
        raise


def _test_set_matches_corpus(test_set_path: Path, df: pd.DataFrame) -> bool:
    if not test_set_path.exists():
        return False
    try:
        items = read_json(test_set_path)
        corpus_ids = set(df["paper_id"].astype(str))
        return bool(items) and all(set(item["ground_truth_doc_ids"]) <= corpus_ids for item in items)
    except (KeyError, TypeError, ValueError):
        return False

def main() -> None:
    """Run the complete clean-data baseline and persist all evidence artifacts."""
    settings = load_settings()
    records, source_mode = _load_or_fetch_records(settings)
    clean_df = build_clean_dataframe(records, run_date=now_utc())
    if len(clean_df) < 4:
        raise RuntimeError(f"Cleaning produced only {len(clean_df)} records; at least four are required.")
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))

    index = LocalEmbeddingIndex.build(clean_df, settings, settings.paths.embeddings_json)
    if settings.refresh_test_set or not _test_set_matches_corpus(settings.paths.eval_testset, clean_df):
        test_set = build_test_set(clean_df, settings.paths.eval_testset)
    else:
        test_set = read_json(settings.paths.eval_testset)

    evaluation = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    quality = run_data_quality_checks(clean_df, settings, "baseline_quality")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)

    source_summary = {
        "source": settings.source_api,
        "source_mode": source_mode,
        "api_url": CROSSREF_API_URL,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "max_results": settings.max_results,
        "raw_record_count": len(records),
        "clean_record_count": len(clean_df),
        "raw_response_path": str(settings.paths.raw_api_response.relative_to(settings.paths.project_dir)),
        "raw_records_path": str(settings.paths.raw_records_json.relative_to(settings.paths.project_dir)),
        "clean_schema": list(clean_df.columns),
    }
    generate_phase1_report(settings.paths.baseline_report, source_summary, evaluation.summary, quality, freshness)

    demo_payload: dict = {
        "provider": settings.llm_provider,
        "model": settings.model_name,
        "question": test_set[0]["question"],
    }
    try:
        agent = build_agent(settings, index)
        demo_payload.update({"status": "success", "answer": run_agent_question(agent, test_set[0]["question"])})
    except Exception as exc:
        # Do not persist provider error text because SDK messages can contain
        # request metadata. Evaluation remains fully reproducible without it.
        demo_payload.update({"status": "unavailable", "error_type": type(exc).__name__})
    write_json(settings.paths.demo_answers, demo_payload)

    print(f"Baseline complete: {len(clean_df)} clean records, {len(test_set)} evaluation samples.")
    print(f"Metrics: {settings.paths.baseline_metrics}")
    print(f"Report: {settings.paths.baseline_report}")
