from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

import pandas as pd

from core.config import Settings, load_settings
from core.utils import ArtifactValidationError, file_sha256, write_csv, write_json, write_text
from ingestion.crossref import PaperRecord
from pipelines.corruption_flow import main
from pipelines.phase1 import _dataframe_records


RUN_DATE = datetime(2026, 5, 12, tzinfo=UTC)


def _record() -> PaperRecord:
    return PaperRecord(
        paper_id="10.1000/abc",
        title="Agentic Retrieval",
        summary="A retrieval method.",
        authors=["Ada Lovelace"],
        categories=["Retrieval"],
        primary_category="Retrieval",
        published="2026-05-02",
        updated="2026-05-03",
        abs_url="https://doi.org/10.1000/abc",
        pdf_url="https://example.org/paper.pdf",
        comment="Example Publisher",
    )


def _clean_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "paper_id": "10.1000/abc",
                "title": "Agentic Retrieval",
                "summary": "A retrieval method.",
                "summary_chars": 19,
                "published": "2026-05-02",
                "age_days": 10,
                "authors_joined": "Ada Lovelace",
                "categories_joined": "Retrieval",
                "text_for_embedding": "Agentic Retrieval. A retrieval method.",
                "abs_url": "https://doi.org/10.1000/abc",
                "pdf_url": "https://example.org/paper.pdf",
            }
        ]
    )


def _test_set() -> list[dict]:
    return [
        {
            "id": "q-1",
            "question_type": "summary",
            "question": "What is the paper about?",
            "ground_truth": "A retrieval method.",
            "ground_truth_doc_ids": ["10.1000/abc"],
        }
    ]


def _write_baseline(settings: Settings) -> None:
    clean_df = _clean_dataframe()
    write_json(settings.paths.raw_api_response, {"message": {"items": [{}]}})
    write_json(
        settings.paths.raw_request_metadata,
        {
            "source": settings.source_api,
            "fetched_at_utc": "2026-05-12T00:00:00+00:00",
            "request": {"query": settings.source_query},
        },
    )
    write_json(settings.paths.raw_records_json, [asdict(_record())])
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))
    write_json(
        settings.paths.embeddings_json,
        {
            "embedding_model": settings.embedding_model,
            "collection_name": settings.baseline_collection_name,
            "documents": [{"paper_id": "10.1000/abc"}],
        },
    )
    write_json(settings.paths.eval_testset, _test_set())
    write_json(settings.paths.baseline_metrics, {"retrieval_hit_rate": 1.0})
    write_json(settings.paths.baseline_answers, [{"id": "q-1", "retrieval_hit": True}])
    write_json(settings.paths.baseline_quality_report, {"success": True})
    write_json(settings.paths.baseline_freshness_report, {"is_fresh": True})
    write_text(settings.paths.baseline_report, "# Baseline report\n")
    write_json(
        settings.paths.baseline_run_metadata,
        {
            "schema_version": 1,
            "run_date_utc": RUN_DATE.isoformat(),
            "raw_response_sha256": file_sha256(settings.paths.raw_api_response),
            "raw_records_sha256": file_sha256(settings.paths.raw_records_json),
            "clean_json_sha256": file_sha256(settings.paths.clean_json),
            "test_set_sha256": file_sha256(settings.paths.eval_testset),
            "embedding_model": settings.embedding_model,
            "collection_name": settings.baseline_collection_name,
            "top_k": settings.top_k,
            "evaluator_provider": settings.llm_provider,
            "evaluator_model": settings.model_name,
        },
    )


def _corrupted_dataframe() -> pd.DataFrame:
    return _clean_dataframe().assign(
        title="Agentic Retrieval [noise]",
        summary="",
        summary_chars=0,
        text_for_embedding="Agentic Retrieval [noise]. injected noise",
    )


class CorruptionFlowOrchestrationTests(TestCase):
    def test_flow_uses_locked_inputs_and_writes_separate_state_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(project_dir=Path(temp_dir))
            _write_baseline(settings)
            baseline_paths = (
                settings.paths.raw_records_json,
                settings.paths.clean_json,
                settings.paths.embeddings_json,
                settings.paths.eval_testset,
                settings.paths.baseline_metrics,
            )
            baseline_hashes = {path: file_sha256(path) for path in baseline_paths}
            metrics_by_path = {
                settings.paths.corrupted_metrics: {"retrieval_hit_rate": 0.0},
                settings.paths.repaired_metrics: {"retrieval_hit_rate": 1.0},
            }

            def corruption_side_effect(_df, output_log_path):
                write_json(output_log_path, [{"kind": "blank_summary", "paper_id": "10.1000/abc"}])
                return _corrupted_dataframe()

            def index_side_effect(df, settings, embeddings_output_path):
                collection = (
                    settings.corrupted_collection_name
                    if embeddings_output_path == settings.paths.corrupted_embeddings_json
                    else settings.repaired_collection_name
                )
                write_json(
                    embeddings_output_path,
                    {
                        "embedding_model": settings.embedding_model,
                        "collection_name": collection,
                        "documents": [{"paper_id": row["paper_id"]} for row in _dataframe_records(df)],
                    },
                )
                return SimpleNamespace(collection_name=collection)

            def evaluation_side_effect(**kwargs):
                summary = metrics_by_path[kwargs["metrics_output_path"]]
                write_json(kwargs["metrics_output_path"], summary)
                write_json(kwargs["answers_output_path"], [{"id": "q-1"}])
                return SimpleNamespace(summary=summary)

            def quality_side_effect(_df, settings, report_name):
                payload = {"success": report_name == "repaired_quality", "state": report_name}
                path = (
                    settings.paths.corrupted_quality_report
                    if report_name == "corrupted_quality"
                    else settings.paths.repaired_quality_report
                )
                write_json(path, payload)
                return payload

            def freshness_side_effect(_df, settings, report_path):
                payload = {"state": report_path.stem, "threshold": settings.freshness_threshold_days}
                write_json(report_path, payload)
                return payload

            def report_side_effect(report_path, **_kwargs):
                write_text(report_path, "# Corruption comparison\n")

            with (
                patch("pipelines.corruption_flow.load_settings", return_value=settings),
                patch(
                    "pipelines.corruption_flow.corrupt_clean_dataframe",
                    side_effect=corruption_side_effect,
                ) as corrupt,
                patch("pipelines.corruption_flow.LocalEmbeddingIndex.build", side_effect=index_side_effect) as build_index,
                patch("pipelines.corruption_flow.evaluate_pipeline", side_effect=evaluation_side_effect) as evaluate,
                patch("pipelines.corruption_flow.run_data_quality_checks", side_effect=quality_side_effect),
                patch("pipelines.corruption_flow.build_freshness_report", side_effect=freshness_side_effect),
                patch("pipelines.corruption_flow.load_raw_records", return_value=[_record()]) as load_raw,
                patch("pipelines.corruption_flow.build_clean_dataframe", return_value=_clean_dataframe()) as clean,
                patch("pipelines.corruption_flow.generate_corruption_report", side_effect=report_side_effect) as report,
            ):
                main()

            corrupt.assert_called_once()
            self.assertEqual(build_index.call_count, 2)
            self.assertEqual(evaluate.call_count, 2)
            for call in evaluate.call_args_list:
                self.assertEqual(call.kwargs["test_set_path"], settings.paths.eval_testset)
            load_raw.assert_called_once_with(settings.paths.raw_records_json)
            self.assertEqual(clean.call_args.kwargs["run_date"], RUN_DATE)
            report.assert_called_once()
            self.assertTrue(settings.paths.corrupted_clean_json.exists())
            self.assertTrue(settings.paths.repaired_clean_json.exists())
            self.assertTrue(settings.paths.comparison_report.exists())
            for path, expected_hash in baseline_hashes.items():
                self.assertEqual(file_sha256(path), expected_hash)

    def test_flow_rejects_missing_baseline_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(project_dir=Path(temp_dir))
            _write_baseline(settings)
            settings.paths.baseline_run_metadata.unlink()

            with patch("pipelines.corruption_flow.load_settings", return_value=settings):
                with self.assertRaisesRegex(ArtifactValidationError, "baseline run metadata"):
                    main()

    def test_flow_rejects_repair_that_differs_from_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(project_dir=Path(temp_dir))
            _write_baseline(settings)

            def corruption_side_effect(_df, output_log_path):
                write_json(output_log_path, [{"kind": "noise"}])
                return _corrupted_dataframe()

            def index_side_effect(df, settings, embeddings_output_path):
                write_json(
                    embeddings_output_path,
                    {
                        "embedding_model": settings.embedding_model,
                        "collection_name": settings.corrupted_collection_name,
                        "documents": [{} for _ in range(len(df))],
                    },
                )
                return object()

            def evaluation_side_effect(**kwargs):
                summary = {"retrieval_hit_rate": 0.0}
                write_json(kwargs["metrics_output_path"], summary)
                write_json(kwargs["answers_output_path"], [{"id": "q-1"}])
                return SimpleNamespace(summary=summary)

            def quality_side_effect(_df, settings, report_name):
                payload = {"state": report_name}
                write_json(settings.paths.corrupted_quality_report, payload)
                return payload

            def freshness_side_effect(_df, settings, report_path):
                payload = {"is_fresh": False}
                write_json(report_path, payload)
                return payload

            mismatched_repair = _clean_dataframe().assign(title="Different canonical title")
            with (
                patch("pipelines.corruption_flow.load_settings", return_value=settings),
                patch("pipelines.corruption_flow.corrupt_clean_dataframe", side_effect=corruption_side_effect),
                patch("pipelines.corruption_flow.LocalEmbeddingIndex.build", side_effect=index_side_effect),
                patch("pipelines.corruption_flow.evaluate_pipeline", side_effect=evaluation_side_effect),
                patch("pipelines.corruption_flow.run_data_quality_checks", side_effect=quality_side_effect),
                patch("pipelines.corruption_flow.build_freshness_report", side_effect=freshness_side_effect),
                patch("pipelines.corruption_flow.load_raw_records", return_value=[_record()]),
                patch("pipelines.corruption_flow.build_clean_dataframe", return_value=mismatched_repair),
            ):
                with self.assertRaisesRegex(ArtifactValidationError, "canonical content"):
                    main()
