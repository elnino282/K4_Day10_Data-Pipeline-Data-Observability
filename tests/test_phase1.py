from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

import pandas as pd

from core.config import load_settings
from ingestion.crossref import PaperRecord
from pipelines.phase1 import main


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

            with (
                patch("pipelines.phase1.load_settings", return_value=settings),
                patch("pipelines.phase1.fetch_source_records", return_value=records) as fetch,
                patch("pipelines.phase1.build_clean_dataframe", return_value=clean_df) as clean,
                patch("pipelines.phase1.LocalEmbeddingIndex.build", return_value=object()) as build_index,
                patch("pipelines.phase1.build_test_set", return_value=test_set) as build_test,
                patch("pipelines.phase1.evaluate_pipeline", return_value=evaluation) as evaluate,
                patch("pipelines.phase1.run_data_quality_checks", return_value={"success": True}) as quality,
                patch("pipelines.phase1.build_freshness_report", return_value={"is_fresh": True}) as freshness,
                patch("pipelines.phase1.generate_phase1_report") as report,
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

    def test_phase1_requires_age_days_in_clean_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(project_dir=Path(temp_dir))
            invalid_df = _clean_dataframe().drop(columns=["age_days"])

            with (
                patch("pipelines.phase1.load_settings", return_value=settings),
                patch("pipelines.phase1.fetch_source_records", return_value=[_record()]),
                patch("pipelines.phase1.build_clean_dataframe", return_value=invalid_df),
            ):
                with self.assertRaisesRegex(ValueError, "age_days"):
                    main()
