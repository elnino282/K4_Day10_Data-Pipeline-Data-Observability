from __future__ import annotations

import hashlib
import json

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", force_ascii=False))


def _metric_delta(left: dict, right: dict) -> dict[str, float]:
    names = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]
    return {name: round(float(right[name]) - float(left[name]), 6) for name in names}

def main() -> None:
    """Measure deterministic corruption impact, repair from raw, and compare."""
    settings = load_settings()
    required = [
        settings.paths.clean_json,
        settings.paths.raw_records_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Run the baseline pipeline first; missing artifacts: {missing}")

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    baseline_df = pd.DataFrame(read_json(settings.paths.clean_json))
    corrupted_df = corrupt_clean_dataframe(baseline_df, settings.paths.corruption_log)
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, _records(corrupted_df))
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df, settings, settings.paths.corrupted_embeddings_json
    )
    corrupted_eval = evaluate_pipeline(
        settings,
        corrupted_index,
        settings.paths.eval_testset,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted_quality")
    corrupted_freshness_path = settings.paths.quality_dir / "corrupted_freshness_report.json"
    corrupted_freshness = build_freshness_report(corrupted_df, settings, corrupted_freshness_path)

    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, _records(repaired_df))
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df, settings, settings.paths.repaired_embeddings_json
    )
    repaired_eval = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired_quality")
    repaired_freshness_path = settings.paths.quality_dir / "repaired_freshness_report.json"
    repaired_freshness = build_freshness_report(repaired_df, settings, repaired_freshness_path)

    baseline_quality_path = settings.paths.quality_dir / "baseline_quality.json"
    baseline_quality = read_json(baseline_quality_path) if baseline_quality_path.exists() else None
    baseline_freshness = read_json(settings.paths.freshness_report) if settings.paths.freshness_report.exists() else None
    baseline_ids = set(baseline_df["paper_id"].astype(str))
    repaired_ids = set(repaired_df["paper_id"].astype(str))
    repair_validation = {
        "baseline_rows": len(baseline_df),
        "repaired_rows": len(repaired_df),
        "baseline_unique_ids": len(baseline_ids),
        "repaired_unique_ids": len(repaired_ids),
        "missing_after_repair": sorted(baseline_ids - repaired_ids),
        "unexpected_after_repair": sorted(repaired_ids - baseline_ids),
        "document_identity_restored": baseline_ids == repaired_ids,
    }
    write_json(settings.paths.quality_dir / "repair_validation.json", repair_validation)

    test_set_sha256 = hashlib.sha256(settings.paths.eval_testset.read_bytes()).hexdigest()
    comparison = {
        "evaluation_set": str(settings.paths.eval_testset.relative_to(settings.paths.project_dir)),
        "evaluation_set_sha256": test_set_sha256,
        "baseline": baseline_metrics,
        "corrupted": corrupted_eval.summary,
        "repaired": repaired_eval.summary,
        "delta_corrupted_vs_baseline": _metric_delta(baseline_metrics, corrupted_eval.summary),
        "delta_repaired_vs_corrupted": _metric_delta(corrupted_eval.summary, repaired_eval.summary),
        "quality": {
            "baseline": baseline_quality,
            "corrupted": corrupted_quality,
            "repaired": repaired_quality,
        },
        "freshness": {
            "baseline": baseline_freshness,
            "corrupted": corrupted_freshness,
            "repaired": repaired_freshness,
        },
        "repair_validation": repair_validation,
    }
    write_json(settings.paths.baseline_metrics.parent / "comparison_metrics.json", comparison)
    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics,
        corrupted_eval.summary,
        repaired_eval.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
    )

    print("Corruption and repair flow complete.")
    print(f"Comparison: {settings.paths.baseline_metrics.parent / 'comparison_metrics.json'}")
    print(f"Report: {settings.paths.comparison_report}")
