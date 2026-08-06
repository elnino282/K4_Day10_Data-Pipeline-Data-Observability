from __future__ import annotations

from collections import Counter
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd

from core.config import Settings, load_settings, normalized_provider
from core.utils import file_sha256, read_json
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


STATE_LABELS = {
    "baseline": "Ban đầu",
    "corrupted": "Bị lỗi",
    "repaired": "Phục hồi",
}

QUESTION_TYPE_LABELS = {
    "summary": "Tóm tắt",
    "authors": "Tác giả",
    "publication_date": "Ngày xuất bản",
    "categories": "Chủ đề",
    "comparison": "So sánh",
    "freshness": "Độ mới",
    "lookup": "Tra cứu",
    "synthesis": "Tổng hợp",
}


class PipelineWorkspace:
    """Read persisted pipeline evidence and provide a small UI-facing contract."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._indexes: dict[str, LocalEmbeddingIndex] = {}
        self._agents: dict[str, Any] = {}
        self._index_lock = Lock()

    def _state_paths(self, state: str) -> dict[str, Path]:
        if state not in STATE_LABELS:
            raise ValueError(f"Trạng thái dữ liệu không hợp lệ: {state}")
        paths = self.settings.paths
        return {
            "baseline": {
                "clean": paths.clean_json,
                "manifest": paths.embeddings_json,
                "metrics": paths.baseline_metrics,
                "answers": paths.baseline_answers,
                "quality": paths.baseline_quality_report,
                "freshness": paths.baseline_freshness_report,
            },
            "corrupted": {
                "clean": paths.corrupted_clean_json,
                "manifest": paths.corrupted_embeddings_json,
                "metrics": paths.corrupted_metrics,
                "answers": paths.corrupted_answers,
                "quality": paths.corrupted_quality_report,
                "freshness": paths.corrupted_freshness_report,
            },
            "repaired": {
                "clean": paths.repaired_clean_json,
                "manifest": paths.repaired_embeddings_json,
                "metrics": paths.repaired_metrics,
                "answers": paths.repaired_answers,
                "quality": paths.repaired_quality_report,
                "freshness": paths.repaired_freshness_report,
            },
        }[state]

    @staticmethod
    def _required_json(path: Path, expected_type: type) -> Any:
        if not path.is_file():
            raise FileNotFoundError(f"Thiếu artifact pipeline: {path}")
        payload = read_json(path)
        if not isinstance(payload, expected_type):
            raise ValueError(
                f"Artifact {path.name} phải có kiểu {expected_type.__name__}."
            )
        return payload

    @staticmethod
    def _percentage(value: Any) -> float:
        return round(100.0 * float(value or 0.0), 1)

    def _paper_payloads(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [str(row.get("paper_id", "")).strip().lower() for row in rows]
        duplicate_ids = {
            paper_id for paper_id, count in Counter(ids).items() if paper_id and count > 1
        }
        papers: list[dict[str, Any]] = []
        for row in rows:
            paper_id = str(row.get("paper_id", ""))
            age_days = row.get("age_days")
            is_stale = isinstance(age_days, (int, float)) and (
                age_days > self.settings.freshness_threshold_days
            )
            has_issue = (
                paper_id.strip().lower() in duplicate_ids
                or not str(row.get("title", "")).strip()
                or not str(row.get("summary", "")).strip()
            )
            papers.append(
                {
                    "id": paper_id,
                    "title": str(row.get("title", "Không có tiêu đề")),
                    "authors": str(row.get("authors_joined", "Không rõ tác giả")),
                    "published": str(row.get("published", "Không rõ")),
                    "category": str(
                        row.get("categories_joined")
                        or row.get("primary_category")
                        or "Chưa phân loại"
                    ),
                    "score": 1.0,
                    "status": "issue" if has_issue else "stale" if is_stale else "healthy",
                    "summary": str(row.get("summary", "")),
                    "url": str(row.get("abs_url") or row.get("pdf_url") or ""),
                }
            )
        return papers

    def _evaluation_payloads(self, answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in answers:
            judge = item.get("judge") if isinstance(item.get("judge"), dict) else {}
            items.append(
                {
                    "id": str(item.get("id", "")),
                    "type": QUESTION_TYPE_LABELS.get(
                        str(item.get("question_type", "")),
                        str(item.get("question_type", "Khác")),
                    ),
                    "question": str(item.get("question", "")),
                    "hit": bool(item.get("retrieval_hit")),
                    "score": float(judge.get("score", 0.0) or 0.0),
                }
            )
        return items

    def _comparison_payloads(self) -> list[dict[str, Any]]:
        metrics = {
            state: self._required_json(self._state_paths(state)["metrics"], dict)
            for state in STATE_LABELS
        }
        return [
            {
                "label": "Truy xuất đúng",
                "baseline": self._percentage(metrics["baseline"].get("retrieval_hit_rate")),
                "corrupted": self._percentage(metrics["corrupted"].get("retrieval_hit_rate")),
                "repaired": self._percentage(metrics["repaired"].get("retrieval_hit_rate")),
                "suffix": "%",
            },
            {
                "label": "Độ chính xác đánh giá",
                "baseline": self._percentage(metrics["baseline"].get("judge_accuracy")),
                "corrupted": self._percentage(metrics["corrupted"].get("judge_accuracy")),
                "repaired": self._percentage(metrics["repaired"].get("judge_accuracy")),
                "suffix": "%",
            },
            {
                "label": "Token F1",
                "baseline": self._percentage(metrics["baseline"].get("mean_token_f1")),
                "corrupted": self._percentage(metrics["corrupted"].get("mean_token_f1")),
                "repaired": self._percentage(metrics["repaired"].get("mean_token_f1")),
                "suffix": "",
            },
        ]

    def workspace(self, state: str) -> dict[str, Any]:
        paths = self._state_paths(state)
        rows = self._required_json(paths["clean"], list)
        metrics = self._required_json(paths["metrics"], dict)
        answers = self._required_json(paths["answers"], list)
        quality = self._required_json(paths["quality"], dict)
        freshness = self._required_json(paths["freshness"], dict)
        manifest = self._required_json(paths["manifest"], dict)

        statistics = quality.get("statistics", {})
        quality_passed = int(statistics.get("successful_checks", 0) or 0)
        quality_total = int(statistics.get("evaluated_checks", 0) or 0)
        fresh_records = int(freshness.get("fresh_rows", 0) or 0)
        paper_count = len(rows)
        hit_rate = float(metrics.get("retrieval_hit_rate", 0.0) or 0.0)
        quality_ratio = quality_passed / quality_total if quality_total else 0.0
        freshness_ratio = fresh_records / paper_count if paper_count else 0.0
        trust_score = round(100 * (0.5 * hit_rate + 0.3 * quality_ratio + 0.2 * freshness_ratio))

        baseline_metrics = self._required_json(
            self.settings.paths.baseline_metrics,
            dict,
        )
        baseline_hit = float(baseline_metrics.get("retrieval_hit_rate", 0.0) or 0.0)
        delta_points = round(100 * (hit_rate - baseline_hit), 1)
        if state == "baseline":
            hit_delta = "Mốc tham chiếu ban đầu"
        elif delta_points >= 0:
            hit_delta = f"Tăng {delta_points:g} điểm so với ban đầu"
        else:
            hit_delta = f"Giảm {abs(delta_points):g} điểm so với ban đầu"

        papers = self._paper_payloads(rows)
        evaluations = self._evaluation_payloads(answers)
        sample = answers[0] if answers else {}
        source_ids = [str(value) for value in sample.get("retrieved_doc_ids", [])]
        paper_by_id = {paper["id"]: paper for paper in papers}
        sample_sources = [paper_by_id[value] for value in source_ids if value in paper_by_id][:2]

        return {
            "sourceMode": "Dữ liệu pipeline",
            "rawHash": file_sha256(self.settings.paths.raw_records_json)[:8],
            "embeddingModel": str(manifest.get("embedding_model", self.settings.embedding_model)),
            "topK": self.settings.top_k,
            "state": {
                "label": STATE_LABELS[state],
                "collection": str(manifest.get("collection_name", f"papers-{state}")),
                "paperCount": paper_count,
                "hitRate": self._percentage(hit_rate),
                "accuracy": self._percentage(metrics.get("judge_accuracy")),
                "tokenF1": float(metrics.get("mean_token_f1", 0.0) or 0.0),
                "judgeScore": float(metrics.get("mean_judge_score", 0.0) or 0.0),
                "qualityPassed": quality_passed,
                "qualityTotal": quality_total,
                "freshRecords": fresh_records,
                "trustScore": trust_score,
                "trustLabel": (
                    "Ngữ cảnh tốt"
                    if trust_score >= 85
                    else "Ngữ cảnh cần chú ý"
                    if trust_score >= 65
                    else "Ngữ cảnh suy giảm"
                ),
                "hitDelta": hit_delta,
                "qualityLabel": (
                    "Tất cả kiểm tra đều đạt"
                    if quality.get("overall_success")
                    else f"{quality_total - quality_passed} kiểm tra cần xử lý"
                ),
                "freshLabel": f"{paper_count - fresh_records} bản ghi vượt ngưỡng tuổi",
            },
            "papers": papers,
            "evaluations": evaluations,
            "comparisonMetrics": self._comparison_payloads(),
            "sampleQuestion": str(sample.get("question", "")),
            "sampleAnswer": str(sample.get("answer", "")),
            "sampleSources": sample_sources,
        }

    def _load_or_build_index(self, state: str) -> LocalEmbeddingIndex:
        with self._index_lock:
            if state in self._indexes:
                return self._indexes[state]

            paths = self._state_paths(state)
            manifest = self._required_json(paths["manifest"], dict)
            indexed_model = str(manifest.get("embedding_model", ""))
            persisted = Path(str(manifest.get("persist_path", "")))
            if not persisted.is_absolute():
                persisted = self.settings.paths.project_dir / persisted
            can_load = (
                indexed_model == self.settings.embedding_model
                and persisted.resolve() == self.settings.paths.chroma_dir.resolve()
                and self.settings.paths.chroma_dir.exists()
            )
            index: LocalEmbeddingIndex | None = None
            if can_load:
                try:
                    index = LocalEmbeddingIndex.load(
                        self.settings,
                        embeddings_path=paths["manifest"],
                    )
                except Exception:
                    index = None

            if index is None:
                rows = self._required_json(paths["clean"], list)
                index = LocalEmbeddingIndex.build(
                    pd.DataFrame(rows),
                    settings=self.settings,
                    embeddings_output_path=paths["manifest"],
                )
            self._indexes[state] = index
            return index

    @staticmethod
    def _normalize_agent_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    chunks.append(str(item["text"]))
                elif isinstance(item, str):
                    chunks.append(item)
            return "\n".join(chunks)
        return str(content or "")

    def chat(self, question: str, state: str) -> dict[str, Any]:
        question = re.sub(r"\s+", " ", question).strip()
        if not question:
            raise ValueError("Câu hỏi không được để trống.")
        if len(question) > 2000:
            raise ValueError("Câu hỏi không được vượt quá 2.000 ký tự.")

        index = self._load_or_build_index(state)
        retrieved = index.search(question, top_k=self.settings.top_k)
        mode = "agent"
        try:
            if state not in self._agents:
                self._agents[state] = build_agent(self.settings, index)
            answer = self._normalize_agent_content(
                run_agent_question(self._agents[state], question)
            )
            if not answer:
                raise RuntimeError("Agent không trả về nội dung.")
        except Exception:
            mode = "trích xuất dự phòng"
            answer = answer_question(
                question,
                settings=self.settings,
                index=index,
                top_k=self.settings.top_k,
            ).answer

        sources = [
            {
                "id": item.paper_id,
                "title": item.title,
                "authors": str(item.metadata.get("authors_joined", "")),
                "published": str(item.metadata.get("published", "")),
                "category": str(
                    item.metadata.get("categories_joined")
                    or item.metadata.get("primary_category")
                    or "Chưa phân loại"
                ),
                "score": round(float(item.score), 4),
                "status": "healthy",
                "summary": str(item.metadata.get("summary", "")),
                "url": str(item.metadata.get("abs_url") or item.metadata.get("pdf_url") or ""),
            }
            for item in retrieved
        ]
        return {
            "answer": answer,
            "sources": sources,
            "state": state,
            "mode": mode,
        }

    def health(self) -> dict[str, Any]:
        provider = normalized_provider(self.settings)
        llm_credential_present = {
            "gemini": bool(self.settings.google_api_key),
            "openai": bool(self.settings.openai_api_key),
            "anthropic": bool(self.settings.anthropic_api_key),
            "openrouter": bool(self.settings.openrouter_api_key),
            "ollama": True,
            "custom": bool(self.settings.custom_llm_base_url),
        }.get(provider, False)
        embedding_credential_present = (
            bool(self.settings.openai_api_key)
            if self.settings.embedding_model.startswith("text-embedding-")
            else True
        )
        return {
            "status": "ok",
            "llmProvider": provider,
            "llmModel": self.settings.model_name,
            "embeddingModel": self.settings.embedding_model,
            "llmCredentialPresent": llm_credential_present,
            "embeddingCredentialPresent": embedding_credential_present,
        }


class PaperLensRequestHandler(SimpleHTTPRequestHandler):
    workspace_service: PipelineWorkspace

    def _write_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _write_error(self, exc: Exception, status: HTTPStatus) -> None:
        self._write_json({"error": str(exc)}, status=status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                self._write_json(self.workspace_service.health())
                return
            if parsed.path == "/api/workspace":
                state = parse_qs(parsed.query).get("state", ["baseline"])[0]
                self._write_json(self.workspace_service.workspace(state))
                return
        except (FileNotFoundError, ValueError) as exc:
            self._write_error(exc, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._write_error(exc, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/chat":
            self._write_json({"error": "Không tìm thấy endpoint."}, HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 64 * 1024:
                raise ValueError("Kích thước request không hợp lệ.")
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Nội dung request phải là một JSON object.")
            result = self.workspace_service.chat(
                str(payload.get("question", "")),
                str(payload.get("state", "baseline")),
            )
            self._write_json(result)
        except (json.JSONDecodeError, ValueError) as exc:
            self._write_error(exc, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._write_error(exc, HTTPStatus.INTERNAL_SERVER_ERROR)


def create_server(
    settings: Settings,
    host: str = "127.0.0.1",
    port: int = 4173,
) -> ThreadingHTTPServer:
    ui_dir = settings.paths.project_dir / "ui"
    if not ui_dir.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục UI: {ui_dir}")
    service = PipelineWorkspace(settings)
    handler_class = type(
        "ConfiguredPaperLensHandler",
        (PaperLensRequestHandler,),
        {"workspace_service": service},
    )
    handler = partial(handler_class, directory=str(ui_dir))
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    settings = load_settings()
    host = os.getenv("UI_HOST", "127.0.0.1")
    port = int(os.getenv("UI_PORT", "4173"))
    server = create_server(settings, host=host, port=port)
    print(f"PaperLens đang chạy tại http://{host}:{port}")
    print("Nhấn Ctrl+C để dừng server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
