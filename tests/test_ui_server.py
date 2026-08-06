from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from unittest import TestCase
from urllib.request import urlopen

from core.config import load_settings
from webapp.server import PipelineWorkspace, create_server


PROJECT_DIR = Path(__file__).resolve().parents[1]


class PipelineWorkspaceTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = load_settings(PROJECT_DIR)
        cls.workspace_service = PipelineWorkspace(cls.settings)

    def test_workspace_reads_real_three_state_artifacts(self) -> None:
        baseline = self.workspace_service.workspace("baseline")
        corrupted = self.workspace_service.workspace("corrupted")
        repaired = self.workspace_service.workspace("repaired")

        self.assertEqual(baseline["sourceMode"], "Dữ liệu pipeline")
        self.assertEqual(baseline["state"]["paperCount"], 24)
        self.assertEqual(baseline["state"]["hitRate"], 100.0)
        self.assertEqual(baseline["state"]["qualityPassed"], 13)
        self.assertEqual(corrupted["state"]["hitRate"], 50.0)
        self.assertEqual(corrupted["state"]["qualityPassed"], 11)
        self.assertEqual(corrupted["state"]["freshRecords"], 22)
        self.assertEqual(repaired["state"]["hitRate"], 100.0)
        self.assertEqual(len(baseline["evaluations"]), 24)
        self.assertEqual(len(baseline["comparisonMetrics"]), 3)
        self.assertTrue(baseline["sampleSources"])
        self.assertTrue(baseline["sampleSources"][0]["retrievedText"])
        self.assertEqual(len(baseline["rawHash"]), 8)

    def test_workspace_rejects_unknown_state(self) -> None:
        with self.assertRaisesRegex(ValueError, "Trạng thái dữ liệu"):
            self.workspace_service.workspace("unknown")

    def test_static_ui_exposes_accessible_interaction_contract(self) -> None:
        html = (PROJECT_DIR / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="skip-link"', html)
        self.assertIn('role="log"', html)
        self.assertIn('aria-pressed="true"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-live="polite"', html)

    def test_http_server_serves_static_ui_health_and_workspace(self) -> None:
        server = create_server(self.settings, port=0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(f"{base_url}/", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("PaperLens", response.read().decode("utf-8"))
            with urlopen(f"{base_url}/api/health", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")
                self.assertEqual(health["embeddingModel"], self.settings.embedding_model)
                self.assertNotIn("apiKey", health)
            with urlopen(f"{base_url}/api/workspace?state=corrupted", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload["state"]["label"], "Cố ý làm lỗi")
                self.assertEqual(payload["state"]["hitRate"], 50.0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
