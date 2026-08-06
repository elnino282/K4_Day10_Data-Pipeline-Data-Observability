from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import (
    ArtifactValidationError,
    file_sha256,
    require_file_artifact,
    require_json_artifact,
    write_csv,
    write_json,
)
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import (
    CLEAN_REQUIRED_COLUMNS,
    _dataframe_records,
    _validate_clean_artifacts,
    _validate_clean_dataframe,
)
from retrieval.index import LocalEmbeddingIndex


def _require_nonempty_json(
    path: Path,
    label: str,
    expected_type: type,
) -> Any:
    payload = require_json_artifact(path, label, expected_type)
    if not payload:
        raise ArtifactValidationError(f"Empty {label} payload: {path}")
    return payload


def _load_clean_dataframe(path: Path, state_label: str) -> pd.DataFrame:
    records = _require_nonempty_json(path, f"{state_label} clean JSON", list)
    if not all(isinstance(record, dict) for record in records):
        raise ArtifactValidationError(
            f"Invalid {state_label} clean JSON: every row must be an object."
        )
    return pd.DataFrame(records)


def _validate_corrupted_dataframe(df: pd.DataFrame, baseline_columns: set[str]) -> None:
    """Validate the handoff schema without rejecting intentional corruption."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Corruption must return a pandas DataFrame.")
    if df.empty:
        raise ValueError("Corruption produced an empty dataset; evaluation cannot continue.")
    missing_columns = sorted(CLEAN_REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(
            f"Corrupted dataset is missing required columns: {', '.join(missing_columns)}"
        )
    if set(df.columns) != baseline_columns:
        raise ValueError("Corrupted dataset schema differs from the locked baseline schema.")

    for column in ("paper_id", "title", "text_for_embedding"):
        blank_rows = df[column].fillna("").astype(str).str.strip().eq("")
        if blank_rows.any():
            raise ValueError(
                f"Corrupted dataset contains {int(blank_rows.sum())} blank {column} values."
            )

    age_days = pd.to_numeric(df["age_days"], errors="coerce")
    finite_age = age_days.map(
        lambda value: math.isfinite(float(value)) if pd.notna(value) else False
    )
    if (~finite_age).any():
        raise ValueError("Corrupted dataset contains non-numeric age_days values.")


def _validate_index_manifest(
    path: Path,
    state_label: str,
    expected_collection: str,
    expected_model: str,
    expected_documents: int,
) -> dict[str, Any]:
    manifest = _require_nonempty_json(path, f"{state_label} embedding manifest", dict)
    if manifest.get("collection_name") != expected_collection:
        raise ArtifactValidationError(
            f"{state_label.capitalize()} manifest collection mismatch: expected "
            f"{expected_collection!r}, got {manifest.get('collection_name')!r}."
        )
    if manifest.get("embedding_model") != expected_model:
        raise ArtifactValidationError(
            f"{state_label.capitalize()} manifest embedding model mismatch: expected "
            f"{expected_model!r}, got {manifest.get('embedding_model')!r}."
        )
    documents = manifest.get("documents")
    if not isinstance(documents, list) or len(documents) != expected_documents:
        actual = len(documents) if isinstance(documents, list) else "invalid"
        raise ArtifactValidationError(
            f"{state_label.capitalize()} manifest document count mismatch: expected "
            f"{expected_documents}, got {actual}."
        )
    return manifest


def _parse_and_validate_baseline_lock(
    settings: Settings,
    lock: dict[str, Any],
) -> datetime:
    expected_values = {
        "raw_response_sha256": file_sha256(settings.paths.raw_api_response),
        "raw_records_sha256": file_sha256(settings.paths.raw_records_json),
        "clean_json_sha256": file_sha256(settings.paths.clean_json),
        "test_set_sha256": file_sha256(settings.paths.eval_testset),
        "embedding_model": settings.embedding_model,
        "collection_name": settings.baseline_collection_name,
        "top_k": settings.top_k,
        "evaluator_provider": settings.llm_provider,
        "evaluator_model": settings.model_name,
    }
    mismatches = [
        key
        for key, expected in expected_values.items()
        if lock.get(key) != expected
    ]
    if mismatches:
        raise ArtifactValidationError(
            "Baseline lock no longer matches the current artifacts/settings: "
            f"{', '.join(mismatches)}. Rerun phase1 before corruption flow."
        )

    run_date_value = lock.get("run_date_utc")
    if not isinstance(run_date_value, str):
        raise ArtifactValidationError("Baseline lock is missing run_date_utc.")
    try:
        run_date = datetime.fromisoformat(run_date_value)
    except ValueError as exc:
        raise ArtifactValidationError("Baseline lock contains an invalid run_date_utc.") from exc
    if run_date.tzinfo is None:
        raise ArtifactValidationError("Baseline lock run_date_utc must include a timezone.")
    return run_date


def _canonical_records(df: pd.DataFrame) -> list[str]:
    columns = sorted(df.columns)
    normalized = df.loc[:, columns]
    records = _dataframe_records(normalized)
    return sorted(
        json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        for record in records
    )


def _assert_repaired_matches_baseline(
    baseline_df: pd.DataFrame,
    repaired_df: pd.DataFrame,
) -> None:
    if set(repaired_df.columns) != set(baseline_df.columns):
        raise ArtifactValidationError("Repaired schema does not match the locked baseline schema.")
    if len(repaired_df) != len(baseline_df):
        raise ArtifactValidationError(
            "Repaired row count does not match the locked baseline: "
            f"baseline={len(baseline_df)}, repaired={len(repaired_df)}."
        )

    baseline_ids = set(baseline_df["paper_id"].astype(str).str.strip().str.lower())
    repaired_ids = set(repaired_df["paper_id"].astype(str).str.strip().str.lower())
    if repaired_ids != baseline_ids:
        raise ArtifactValidationError(
            "Repaired paper_id set does not match the locked baseline paper_id set."
        )
    if _canonical_records(repaired_df) != _canonical_records(baseline_df):
        raise ArtifactValidationError(
            "Repaired canonical content does not match the locked baseline content."
        )


def _evaluate_state(
    *,
    settings: Settings,
    state_label: str,
    index: LocalEmbeddingIndex,
    metrics_path: Path,
    answers_path: Path,
) -> dict[str, Any]:
    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=metrics_path,
        answers_output_path=answers_path,
    )
    metrics = _require_nonempty_json(metrics_path, f"{state_label} metrics", dict)
    _require_nonempty_json(answers_path, f"{state_label} answers", list)
    if metrics != evaluation.summary:
        raise ArtifactValidationError(
            f"{state_label.capitalize()} metrics artifact does not match the "
            "evaluation summary returned in memory."
        )
    return metrics


def _observe_state(
    *,
    settings: Settings,
    state_label: str,
    df: pd.DataFrame,
    quality_path: Path,
    freshness_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    quality = run_data_quality_checks(
        df,
        settings=settings,
        report_name=f"{state_label}_quality",
    )
    quality_payload = _require_nonempty_json(
        quality_path,
        f"{state_label} quality report",
        dict,
    )
    if quality_payload != quality:
        raise ArtifactValidationError(
            f"{state_label.capitalize()} quality artifact does not match the "
            "quality result returned in memory."
        )

    freshness = build_freshness_report(
        df,
        settings=settings,
        report_path=freshness_path,
    )
    freshness_payload = _require_nonempty_json(
        freshness_path,
        f"{state_label} freshness report",
        dict,
    )
    if freshness_payload != freshness:
        raise ArtifactValidationError(
            f"{state_label.capitalize()} freshness artifact does not match the "
            "freshness result returned in memory."
        )
    return quality_payload, freshness_payload


def _capture_hashes(paths: tuple[Path, ...]) -> dict[Path, str]:
    return {path: file_sha256(path) for path in paths}


def _assert_hashes_unchanged(expected_hashes: dict[Path, str], checkpoint: str) -> None:
    changed = [
        str(path)
        for path, expected_hash in expected_hashes.items()
        if file_sha256(path) != expected_hash
    ]
    if changed:
        raise ArtifactValidationError(
            f"Locked baseline artifacts changed during {checkpoint}: {', '.join(changed)}"
        )


def main() -> None:
    """Run controlled corruption, rebuild from raw, and compare all three states."""
    settings = load_settings()

    raw_records_payload = _require_nonempty_json(
        settings.paths.raw_records_json,
        "raw parsed records",
        list,
    )
    _require_nonempty_json(settings.paths.raw_api_response, "raw Crossref response", dict)
    _require_nonempty_json(settings.paths.raw_request_metadata, "raw request metadata", dict)
    baseline_df = _load_clean_dataframe(settings.paths.clean_json, "baseline")
    _validate_clean_dataframe(baseline_df)
    _validate_clean_artifacts(
        baseline_df,
        settings.paths.clean_csv,
        settings.paths.clean_json,
        state_label="baseline",
    )
    _validate_index_manifest(
        settings.paths.embeddings_json,
        "baseline",
        settings.baseline_collection_name,
        settings.embedding_model,
        len(baseline_df),
    )
    _require_nonempty_json(settings.paths.eval_testset, "evaluation test set", list)
    baseline_metrics = _require_nonempty_json(
        settings.paths.baseline_metrics,
        "baseline metrics",
        dict,
    )
    _require_nonempty_json(settings.paths.baseline_answers, "baseline answers", list)
    baseline_quality = _require_nonempty_json(
        settings.paths.baseline_quality_report,
        "baseline quality report",
        dict,
    )
    baseline_freshness = _require_nonempty_json(
        settings.paths.baseline_freshness_report,
        "baseline freshness report",
        dict,
    )
    require_file_artifact(settings.paths.baseline_report, "phase 1 Markdown report")
    baseline_lock = _require_nonempty_json(
        settings.paths.baseline_run_metadata,
        "baseline run metadata",
        dict,
    )
    baseline_run_date = _parse_and_validate_baseline_lock(settings, baseline_lock)

    protected_paths = (
        settings.paths.raw_api_response,
        settings.paths.raw_request_metadata,
        settings.paths.raw_records_json,
        settings.paths.clean_csv,
        settings.paths.clean_json,
        settings.paths.embeddings_json,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
        settings.paths.baseline_quality_report,
        settings.paths.baseline_freshness_report,
        settings.paths.baseline_report,
        settings.paths.baseline_run_metadata,
    )
    protected_hashes = _capture_hashes(protected_paths)
    baseline_canonical = _canonical_records(baseline_df)

    corrupted_df = corrupt_clean_dataframe(
        baseline_df.copy(deep=True),
        settings.paths.corruption_log,
    )
    if _canonical_records(baseline_df) != baseline_canonical:
        raise ArtifactValidationError("Corruption mutated the locked baseline dataframe in memory.")
    _validate_corrupted_dataframe(corrupted_df, set(baseline_df.columns))
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, _dataframe_records(corrupted_df))
    _validate_clean_artifacts(
        corrupted_df,
        settings.paths.corrupted_clean_csv,
        settings.paths.corrupted_clean_json,
        state_label="corrupted",
    )
    corruption_log = require_json_artifact(
        settings.paths.corruption_log,
        "corruption log",
    )
    if not isinstance(corruption_log, (dict, list)) or not corruption_log:
        raise ArtifactValidationError(
            "Corruption log must be a non-empty JSON object or array."
        )

    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings=settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    _validate_index_manifest(
        settings.paths.corrupted_embeddings_json,
        "corrupted",
        settings.corrupted_collection_name,
        settings.embedding_model,
        len(corrupted_df),
    )
    corrupted_metrics = _evaluate_state(
        settings=settings,
        state_label="corrupted",
        index=corrupted_index,
        metrics_path=settings.paths.corrupted_metrics,
        answers_path=settings.paths.corrupted_answers,
    )
    corrupted_quality, corrupted_freshness = _observe_state(
        settings=settings,
        state_label="corrupted",
        df=corrupted_df,
        quality_path=settings.paths.corrupted_quality_report,
        freshness_path=settings.paths.corrupted_freshness_report,
    )
    _assert_hashes_unchanged(protected_hashes, "corrupted-state processing")

    if file_sha256(settings.paths.raw_records_json) != baseline_lock["raw_records_sha256"]:
        raise ArtifactValidationError("Raw snapshot changed before repair; recovery was stopped.")
    raw_records = load_raw_records(settings.paths.raw_records_json)
    if not raw_records or len(raw_records) != len(raw_records_payload):
        raise ArtifactValidationError(
            "Reloaded raw records do not match the locked raw snapshot count."
        )
    repaired_df = build_clean_dataframe(raw_records, run_date=baseline_run_date)
    _validate_clean_dataframe(repaired_df)
    _assert_repaired_matches_baseline(baseline_df, repaired_df)
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, _dataframe_records(repaired_df))
    _validate_clean_artifacts(
        repaired_df,
        settings.paths.repaired_clean_csv,
        settings.paths.repaired_clean_json,
        state_label="repaired",
    )

    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings=settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    _validate_index_manifest(
        settings.paths.repaired_embeddings_json,
        "repaired",
        settings.repaired_collection_name,
        settings.embedding_model,
        len(repaired_df),
    )
    repaired_metrics = _evaluate_state(
        settings=settings,
        state_label="repaired",
        index=repaired_index,
        metrics_path=settings.paths.repaired_metrics,
        answers_path=settings.paths.repaired_answers,
    )
    repaired_quality, repaired_freshness = _observe_state(
        settings=settings,
        state_label="repaired",
        df=repaired_df,
        quality_path=settings.paths.repaired_quality_report,
        freshness_path=settings.paths.repaired_freshness_report,
    )
    _assert_hashes_unchanged(protected_hashes, "repaired-state processing")

    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_metrics,
        repaired_metrics=repaired_metrics,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
    )
    require_file_artifact(settings.paths.comparison_report, "corruption comparison report")
    _assert_hashes_unchanged(protected_hashes, "comparison reporting")

    print(
        "Corruption flow completed: "
        f"baseline={len(baseline_df)}, corrupted={len(corrupted_df)}, "
        f"repaired={len(repaired_df)} records."
    )
    print(f"Comparison report: {settings.paths.comparison_report}")
