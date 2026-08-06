from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

import requests

from core.utils import read_json, write_json
from ingestion.crossref import (
    PaperRecord,
    fetch_source_records,
    load_raw_records,
    parse_crossref_payload,
)


def _crossref_payload() -> dict:
    valid_item = {
        "DOI": "10.1000/ABC",
        "title": ["  Agentic   <scp>Retrieval</scp>  "],
        "abstract": "<jats:p>A useful &amp; robust retrieval method.</jats:p>",
        "author": [
            {"given": "Ada", "family": "Lovelace"},
            {"name": "Research Group"},
        ],
        "subject": ["Artificial Intelligence", "Artificial Intelligence", "Retrieval"],
        "published-online": {"date-parts": [[2026, 5, 2]]},
        "indexed": {"date-time": "2026-05-03T10:00:00Z"},
        "URL": "https://doi.org/10.1000/abc",
        "link": [
            {
                "URL": "https://example.org/paper.pdf",
                "content-type": "application/pdf",
            }
        ],
        "publisher": "Example Publisher",
        "container-title": ["Example Journal"],
    }
    duplicate = dict(valid_item)
    duplicate["title"] = ["Duplicate record"]
    invalid_without_abstract = {
        "DOI": "10.1000/missing",
        "title": ["No abstract"],
    }
    return {"message": {"items": [valid_item, duplicate, invalid_without_abstract]}}


class MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class CrossrefParsingTests(TestCase):
    def test_parse_normalizes_and_deduplicates_records(self) -> None:
        records = parse_crossref_payload(_crossref_payload())

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.paper_id, "10.1000/abc")
        self.assertEqual(record.title, "Agentic Retrieval")
        self.assertEqual(record.summary, "A useful & robust retrieval method.")
        self.assertEqual(record.authors, ["Ada Lovelace", "Research Group"])
        self.assertEqual(record.categories, ["Artificial Intelligence", "Retrieval"])
        self.assertEqual(record.published, "2026-05-02")
        self.assertEqual(record.updated, "2026-05-03")
        self.assertEqual(record.pdf_url, "https://example.org/paper.pdf")

    def test_parse_rejects_payload_without_items(self) -> None:
        with self.assertRaisesRegex(ValueError, "message.items"):
            parse_crossref_payload({"message": {}})

    def test_raw_record_round_trip(self) -> None:
        record = parse_crossref_payload(_crossref_payload())[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.json"
            write_json(path, [asdict(record)])

            self.assertEqual(load_raw_records(path), [record])


class CrossrefFetchingTests(TestCase):
    def test_fetch_retries_and_writes_both_raw_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_dir = Path(temp_dir) / "raw"
            settings = SimpleNamespace(
                source_query="agentic rag",
                source_filter="has-abstract:true",
                max_results=24,
                source_api="Crossref REST API",
                paths=SimpleNamespace(
                    raw_api_response=raw_dir / "crossref_response.json",
                    raw_request_metadata=raw_dir / "crossref_request.json",
                    raw_records_json=raw_dir / "crossref_records.json",
                ),
            )
            responses = [MockResponse(503, {}), MockResponse(200, _crossref_payload())]

            with (
                patch("ingestion.crossref.requests.get", side_effect=responses) as request,
                patch("ingestion.crossref.time.sleep") as sleep,
            ):
                records = fetch_source_records(settings)

            self.assertEqual(len(records), 1)
            self.assertEqual(request.call_count, 2)
            sleep.assert_called_once_with(1)
            self.assertEqual(read_json(settings.paths.raw_api_response), _crossref_payload())
            stored_records = read_json(settings.paths.raw_records_json)
            self.assertEqual(stored_records[0]["paper_id"], "10.1000/abc")
            request_metadata = read_json(settings.paths.raw_request_metadata)
            self.assertEqual(request_metadata["request"]["query"], "agentic rag")
            self.assertEqual(request_metadata["request"]["filter"], "has-abstract:true")
            self.assertEqual(request_metadata["request"]["rows"], 24)
            self.assertEqual(request_metadata["api_items"], 3)
            self.assertEqual(request_metadata["usable_records"], 1)
            self.assertIn("fetched_at_utc", request_metadata)

    def test_fetch_does_not_retry_non_transient_http_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_dir = Path(temp_dir) / "raw"
            settings = SimpleNamespace(
                source_query="agentic rag",
                source_filter="has-abstract:true",
                max_results=24,
                source_api="Crossref REST API",
                paths=SimpleNamespace(
                    raw_api_response=raw_dir / "crossref_response.json",
                    raw_request_metadata=raw_dir / "crossref_request.json",
                    raw_records_json=raw_dir / "crossref_records.json",
                ),
            )

            with (
                patch("ingestion.crossref.requests.get", return_value=MockResponse(404, {})) as request,
                patch("ingestion.crossref.time.sleep") as sleep,
            ):
                with self.assertRaisesRegex(RuntimeError, "HTTP status 404"):
                    fetch_source_records(settings)

            request.assert_called_once()
            sleep.assert_not_called()
