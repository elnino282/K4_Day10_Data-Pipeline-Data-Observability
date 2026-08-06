from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

import pandas as pd

from core.config import load_settings
from core.utils import write_json, write_text
from ingestion.crossref import PaperRecord
from pipelines.phase1 import _validate_clean_dataframe, main


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


class Phase1OrchestrationTests(TestCase):
    def test_phase1_hands_artifacts_through_all_baseline_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(project_dir=Path(temp_dir))
            records = [_record()]
            clean_df = _clean_dataframe()
            test_set = [
                {
                    "id": "q-1",
                    "question_type": "summary",
                    "question": "What is the paper about?",
                    "ground_truth": "A retrieval method.",
                    "ground_truth_doc_ids": ["10.1000/abc"],
                }
            ]
            evaluation = SimpleNamespace(summary={"retrieval_hit_rate": 1.0})

            def fetch_side_effect(current_settings):
                write_json(current_settings.paths.raw_api_response, {"message": {"items": [{}]}})
                write_json(
                    current_settings.paths.raw_request_metadata,
                    {
                        "source": current_settings.source_api,
                        "fetched_at_utc": "2026-08-06T00:00:00+00:00",
                        "request": {
                            "query": current_settings.source_query,
                            "filter": current_settings.source_filter,
                            "rows": current_settings.max_results,
                        },
                    },
                )
                write_json(current_settings.paths.raw_records_json, [asdict(item) for item in records])
                return records

            def index_side_effect(*args, **kwargs):
                write_json(kwargs["embeddings_output_path"], {"collection_name": "papers-baseline"})
                return object()

            def test_set_side_effect(_df, output_path):
                write_json(output_path, test_set)
                return test_set

            def evaluation_side_effect(**kwargs):
                write_json(kwargs["metrics_output_path"], evaluation.summary)
                write_json(kwargs["answers_output_path"], [])
                return evaluation

            def quality_side_effect(_df, settings, report_name):
                payload = {"success": True, "report_name": report_name}
                write_json(settings.paths.baseline_quality_report, payload)
                return payload

            def freshness_side_effect(_df, settings, report_path):
                payload = {"is_fresh": True, "threshold": settings.freshness_threshold_days}
                write_json(report_path, payload)
                return payload

            def report_side_effect(report_path, **_kwargs):
                write_text(report_path, "# Baseline report\n")

            with (
                patch("pipelines.phase1.load_settings", return_value=settings),
                patch("pipelines.phase1.fetch_source_records", side_effect=fetch_side_effect) as fetch,
                patch("pipelines.phase1.build_clean_dataframe", return_value=clean_df) as clean,
                patch("pipelines.phase1.LocalEmbeddingIndex.build", side_effect=index_side_effect) as build_index,
                patch("pipelines.phase1.build_test_set", side_effect=test_set_side_effect) as build_test,
                patch("pipelines.phase1.evaluate_pipeline", side_effect=evaluation_side_effect) as evaluate,
                patch("pipelines.phase1.run_data_quality_checks", side_effect=quality_side_effect) as quality,
                patch("pipelines.phase1.build_freshness_report", side_effect=freshness_side_effect) as freshness,
                patch("pipelines.phase1.generate_phase1_report", side_effect=report_side_effect) as report,
            ):
                main()

            fetch.assert_called_once_with(settings)
            clean.assert_called_once()
            build_index.assert_called_once()
            build_test.assert_called_once_with(clean_df, settings.paths.eval_testset)
            evaluate.assert_called_once()
            quality.assert_called_once()
            freshness.assert_called_once()
            report.assert_called_once()
            self.assertTrue(settings.paths.clean_csv.exists())
            self.assertTrue(settings.paths.clean_json.exists())

            source_summary = report.call_args.kwargs["source_summary"]
            self.assertEqual(source_summary["parsed_records"], 1)
            self.assertFalse(source_summary["used_cached_snapshot"])
            self.assertEqual(len(source_summary["raw_records_sha256"]), 64)
            self.assertEqual(len(source_summary["test_set_sha256"]), 64)

    def test_phase1_requires_age_days_in_clean_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(project_dir=Path(temp_dir))
            invalid_df = _clean_dataframe().drop(columns=["age_days"])
            write_json(settings.paths.raw_api_response, {"message": {"items": [{}]}})
            write_json(
                settings.paths.raw_request_metadata,
                {"request": {"query": settings.source_query}},
            )
            write_json(settings.paths.raw_records_json, [asdict(_record())])

            with (
                patch("pipelines.phase1.load_settings", return_value=settings),
                patch("pipelines.phase1.build_clean_dataframe", return_value=invalid_df),
            ):
                with self.assertRaisesRegex(ValueError, "age_days"):
                    main()

    def test_clean_contract_rejects_invalid_identity_and_content(self) -> None:
        cases = [
            (
                "duplicate paper_id",
                pd.concat([_clean_dataframe(), _clean_dataframe()], ignore_index=True),
            ),
            ("blank text_for_embedding", _clean_dataframe().assign(text_for_embedding=" ")),
            ("invalid age_days", _clean_dataframe().assign(age_days=-1)),
            ("summary_chars does not match", _clean_dataframe().assign(summary_chars=999)),
            ("invalid published", _clean_dataframe().assign(published="not-a-date")),
        ]

        for expected_error, dataframe in cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    _validate_clean_dataframe(dataframe)

    def test_freshness_paths_are_distinct_for_all_states(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = load_settings(project_dir=Path(temp_dir)).paths
            freshness_paths = {
                paths.baseline_freshness_report,
                paths.corrupted_freshness_report,
                paths.repaired_freshness_report,
            }
            quality_paths = {
                paths.baseline_quality_report,
                paths.corrupted_quality_report,
                paths.repaired_quality_report,
            }

            self.assertEqual(len(freshness_paths), 3)
            self.assertEqual(len(quality_paths), 3)
