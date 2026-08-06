from __future__ import annotations

from pathlib import Path
import tempfile
from unittest import TestCase

import pandas as pd

from core.utils import read_json
from ingestion.corruption import corrupt_clean_dataframe


def _baseline_dataframe(rows: int = 12) -> pd.DataFrame:
    records = []
    for index in range(rows):
        day = index + 1
        paper_id = f"10.1000/role4-{day:02d}"
        title = f"Reliable Retrieval Observability Case Study {day:02d}"
        summary = (
            f"This paper {day:02d} describes reliable retrieval observability, "
            "quality checks, freshness signals, and repair validation for RAG systems."
        )
        records.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors_joined": f"Author {day:02d}",
                "categories_joined": "Retrieval; Observability",
                "primary_category": "Retrieval",
                "published": f"2026-07-{day:02d}",
                "age_days": 30 - index,
                "summary_chars": len(summary),
                "text_for_embedding": (
                    f"Title: {title}. Abstract: {summary} Authors: Author {day:02d}. "
                    "Topics: Retrieval; Observability. Published: 2026-07."
                ),
                "abs_url": f"https://doi.org/{paper_id}",
                "pdf_url": "",
            }
        )
    return pd.DataFrame(records)


class CorruptCleanDataFrameTests(TestCase):
    def test_corruption_is_deterministic_logged_and_does_not_mutate_baseline(self) -> None:
        baseline = _baseline_dataframe()
        baseline_snapshot = baseline.copy(deep=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "corruption_log.json"
            corrupted = corrupt_clean_dataframe(baseline, log_path)
            log = read_json(log_path)

        pd.testing.assert_frame_equal(baseline, baseline_snapshot)
        self.assertEqual(set(corrupted.columns), set(baseline.columns))
        self.assertEqual(len(corrupted), len(baseline))
        self.assertEqual(corrupted["paper_id"].nunique(), len(baseline) - 2)

        scenarios = {item["scenario"]: item for item in log["scenarios"]}
        self.assertEqual(
            set(scenarios),
            {
                "drop_latest_records",
                "blank_summary",
                "inject_summary_noise",
                "truncate_title",
                "stale_publication_date",
                "duplicate_rows",
            },
        )
        self.assertEqual(
            scenarios["drop_latest_records"]["paper_ids"],
            ["10.1000/role4-12", "10.1000/role4-11"],
        )
        self.assertEqual(log["before_rows"], 12)
        self.assertEqual(log["after_rows"], 12)
        self.assertEqual(log["unique_paper_ids_before"], 12)
        self.assertEqual(log["unique_paper_ids_after"], 10)

    def test_corruption_creates_expected_quality_and_freshness_signals(self) -> None:
        baseline = _baseline_dataframe()

        with tempfile.TemporaryDirectory() as temp_dir:
            corrupted = corrupt_clean_dataframe(
                baseline,
                Path(temp_dir) / "corruption_log.json",
            )

        blank_summary_rows = corrupted["summary"].fillna("").astype(str).eq("")
        duplicated_id_rows = corrupted["paper_id"].duplicated(keep=False)
        stale_rows = pd.to_numeric(corrupted["age_days"], errors="coerce").gt(180)
        noisy_rows = corrupted["summary"].astype(str).str.startswith("UNVERIFIED PIPELINE NOISE")

        self.assertEqual(int(blank_summary_rows.sum()), 2)
        self.assertEqual(int(duplicated_id_rows.sum()), 4)
        self.assertEqual(int(stale_rows.sum()), 2)
        self.assertEqual(int(noisy_rows.sum()), 2)
        self.assertTrue(
            corrupted.loc[noisy_rows, "title"].astype(str).str.len().between(8, 18).all()
        )
        self.assertTrue(
            corrupted["summary_chars"].eq(corrupted["summary"].fillna("").astype(str).str.len()).all()
        )
        self.assertTrue(corrupted["text_for_embedding"].fillna("").astype(str).str.strip().ne("").all())

    def test_corruption_rejects_dataframe_without_required_columns(self) -> None:
        baseline = _baseline_dataframe().drop(columns=["summary_chars"])

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "missing columns"):
                corrupt_clean_dataframe(baseline, Path(temp_dir) / "corruption_log.json")

    def test_corruption_rejects_too_small_dataframe(self) -> None:
        baseline = _baseline_dataframe(rows=5)

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "At least six rows"):
                corrupt_clean_dataframe(baseline, Path(temp_dir) / "corruption_log.json")
