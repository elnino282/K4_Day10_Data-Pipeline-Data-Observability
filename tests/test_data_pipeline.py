from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from core.config import load_settings
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records, parse_crossref_payload
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report, generate_phase1_report
from retrieval.index import SearchResult
from retrieval.qa import _extract_answer


def _paper(position: int) -> PaperRecord:
    return PaperRecord(
        paper_id=f"10.1234/paper-{position}",
        title=f"Reliable Retrieval Study Number {position}",
        summary=(
            f"This study number {position} evaluates retrieval augmented generation "
            "with a reproducible scholarly metadata benchmark."
        ),
        authors=[f"Author {position}", "Shared Researcher"],
        categories=["Artificial Intelligence", "Information Retrieval"],
        primary_category="Artificial Intelligence",
        published=f"2026-08-{position + 1:02d}",
        updated="2026-08-06T00:00:00Z",
        abs_url=f"https://doi.org/10.1234/paper-{position}",
        pdf_url="",
        comment="",
    )


@pytest.fixture
def clean_df() -> pd.DataFrame:
    return build_clean_dataframe([_paper(index) for index in range(8)], datetime(2026, 8, 6, tzinfo=UTC))


def test_parse_crossref_payload_normalizes_markup_and_deduplicates():
    item = {
        "DOI": "10.1000/EXAMPLE",
        "title": ["  A <i>Useful</i> Paper  "],
        "abstract": "<jats:p>An &amp; useful abstract with enough source detail.</jats:p>",
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "subject": ["AI", "AI"],
        "published-online": {"date-parts": [[2026, 7, 2]]},
        "indexed": {"date-time": "2026-07-03T12:00:00Z"},
        "URL": "https://doi.org/10.1000/example",
        "link": [{"URL": "https://example.org/paper.pdf", "content-type": "application/pdf"}],
    }
    records = parse_crossref_payload({"message": {"items": [item, item, {"DOI": "missing-fields"}]}})

    assert len(records) == 1
    assert records[0].paper_id == "10.1000/example"
    assert records[0].title == "A Useful Paper"
    assert records[0].authors == ["Ada Lovelace"]
    assert records[0].categories == ["AI"]
    assert records[0].published == "2026-07-02"
    assert records[0].pdf_url.endswith("paper.pdf")


def test_parse_crossref_rejects_invalid_items_shape():
    with pytest.raises(ValueError, match="message.items"):
        parse_crossref_payload({"message": {"items": "not-a-list"}})


def test_fetch_persists_raw_response_and_normalized_records(tmp_path):
    settings = load_settings(tmp_path)
    response = Mock(status_code=200, headers={})
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/fetch",
                    "title": ["Fetched paper"],
                    "abstract": "A sufficiently detailed abstract returned by the mocked Crossref endpoint.",
                    "published": {"date-parts": [[2026, 8, 1]]},
                }
            ]
        }
    }
    with patch("ingestion.crossref.requests.get", return_value=response):
        records = fetch_source_records(settings)

    assert len(records) == 1
    assert settings.paths.raw_api_response.exists()
    assert settings.paths.raw_records_json.exists()
    assert load_raw_records(settings.paths.raw_records_json) == records


def test_load_raw_records_validates_schema(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"paper_id": "only-one-field"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        load_raw_records(path)


def test_cleaning_creates_canonical_schema_and_deduplicates():
    record = _paper(1)
    df = build_clean_dataframe([record, PaperRecord(**asdict(record))], datetime(2026, 8, 6, tzinfo=UTC))

    assert len(df) == 1
    assert df.loc[0, "age_days"] == 4
    assert df.loc[0, "summary_chars"] == len(df.loc[0, "summary"])
    assert "Title:" in df.loc[0, "text_for_embedding"]
    assert "Abstract:" in df.loc[0, "text_for_embedding"]


def test_cleaning_filters_invalid_records():
    invalid = PaperRecord(**{**asdict(_paper(1)), "summary": "short"})
    df = build_clean_dataframe([invalid], datetime(2026, 8, 6, tzinfo=UTC))
    assert df.empty


def test_testset_is_deterministic_and_covers_four_question_types(clean_df, tmp_path):
    path = tmp_path / "test_set.json"
    first = build_test_set(clean_df, path)
    second = build_test_set(clean_df, path)

    assert first == second
    assert len(first) == 24
    assert {item["question_type"] for item in first} == {
        "summary",
        "authors",
        "publication_date",
        "categories",
    }
    assert all(item["ground_truth_doc_ids"] for item in first)


def test_testset_requires_minimum_corpus(clean_df, tmp_path):
    with pytest.raises(ValueError, match="four"):
        build_test_set(clean_df.head(3), tmp_path / "test_set.json")


def test_corruption_is_auditable_and_triggers_quality_failures(clean_df, tmp_path):
    settings = load_settings(tmp_path)
    log_path = tmp_path / "corruption.json"
    corrupted = corrupt_clean_dataframe(clean_df, log_path)
    quality = run_data_quality_checks(corrupted, settings, "corrupted")
    freshness = build_freshness_report(corrupted, settings, tmp_path / "freshness.json")

    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert {item["scenario"] for item in log["scenarios"]} == {
        "drop_latest_records",
        "blank_summary",
        "inject_summary_noise",
        "truncate_title",
        "stale_publication_date",
        "duplicate_rows",
    }
    assert not quality["overall_success"]
    assert not freshness["is_fresh"]
    assert corrupted["paper_id"].duplicated().any()


def test_clean_data_passes_quality_and_freshness(clean_df, tmp_path):
    settings = load_settings(tmp_path)
    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, tmp_path / "freshness.json")

    assert quality["overall_success"]
    assert quality["statistics"]["success_percent"] == 100.0
    assert freshness["is_fresh"]
    assert (settings.paths.gx_dir / "baseline.json").exists()


def test_quality_handles_missing_schema_without_crashing(tmp_path):
    payload = run_data_quality_checks(pd.DataFrame({"unexpected": [1]}), load_settings(tmp_path), "bad")
    assert not payload["overall_success"]
    assert payload["checks"][0]["name"] == "required_columns"


def test_reports_render_runtime_values(clean_df, tmp_path):
    settings = load_settings(tmp_path)
    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, tmp_path / "freshness.json")
    metrics = {
        "samples": 24,
        "retrieval_hit_rate": 1.0,
        "mean_token_f1": 1.0,
        "judge_accuracy": 1.0,
        "mean_judge_score": 5.0,
        "ragas": {"skipped": "disabled"},
    }
    baseline_report = tmp_path / "baseline.md"
    comparison_report = tmp_path / "comparison.md"
    generate_phase1_report(
        baseline_report,
        {"source": "Crossref", "raw_record_count": 8, "clean_record_count": 8, "clean_schema": list(clean_df)},
        metrics,
        quality,
        freshness,
    )
    corrupted_metrics = {**metrics, "retrieval_hit_rate": 0.5, "mean_token_f1": 0.6}
    generate_corruption_report(
        comparison_report,
        metrics,
        corrupted_metrics,
        metrics,
        quality,
        quality,
        freshness,
        freshness,
        baseline_quality=quality,
        baseline_freshness=freshness,
    )

    assert "Baseline Pipeline Report" in baseline_report.read_text(encoding="utf-8")
    comparison_text = comparison_report.read_text(encoding="utf-8")
    assert "-0.500" in comparison_text
    assert "CONFIRMED" in comparison_text


def test_category_answer_uses_primary_category_when_crossref_subject_is_missing():
    result = SearchResult(
        paper_id="10.1000/example",
        title="Example",
        score=1.0,
        content="Example content",
        metadata={"categories_joined": "", "primary_category": "uncategorized"},
    )
    assert _extract_answer("What categories describe the paper?", result) == "uncategorized"
