from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import math
import os

from core.config import load_settings
from core.utils import read_json, write_json, write_text
from evaluation.metrics import run_ragas
from observability.reporting import generate_corruption_report


RAGAS_METRICS = {
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "faithfulness",
}
RAGAS_INPUT_FIELDS = ("question", "answer", "ground_truth", "retrieved_contexts")


def _state_paths(settings):
    return {
        "baseline": (settings.paths.baseline_answers, settings.paths.baseline_metrics),
        "corrupted": (settings.paths.corrupted_answers, settings.paths.corrupted_metrics),
        "repaired": (settings.paths.repaired_answers, settings.paths.repaired_metrics),
    }


def _evaluate(settings, state: str, answers: list[dict]) -> dict:
    print(f"Running Ragas for {state}: {len(answers)} samples", flush=True)
    result = run_ragas(settings, answers, force=True)
    if "error" in result:
        raise RuntimeError(result["error"])
    print(json.dumps({state: result}, indent=2), flush=True)
    return result


def _input_sha256(answers: list[dict]) -> str:
    payload = [{key: item[key] for key in RAGAS_INPUT_FIELDS} for item in answers]
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_result(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and set(payload) == RAGAS_METRICS
        and all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in payload.values()
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate persisted answer traces with Ragas without rerunning retrieval."
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Evaluate only the first baseline sample and do not modify artifacts.",
    )
    args = parser.parse_args()
    settings = load_settings()
    paths = _state_paths(settings)

    if args.smoke:
        answers = read_json(paths["baseline"][0])[:1]
        _evaluate(settings, "baseline-smoke", answers)
        return

    updated_metrics: dict[str, dict] = {}
    result_cache: dict[str, tuple[dict, str, str]] = {}
    evaluated_at = datetime.now(UTC).isoformat()
    for state, (answers_path, metrics_path) in paths.items():
        answers = read_json(answers_path)
        metrics = read_json(metrics_path)
        input_hash = _input_sha256(answers)
        previous_run = metrics.get("ragas_run", {})
        if (
            _valid_result(metrics.get("ragas"))
            and previous_run.get("input_sha256") == input_hash
            and previous_run.get("evaluator_model") == settings.model_name
            and previous_run.get("embedding_model") == settings.embedding_model
        ):
            ragas_result = metrics["ragas"]
            source_state = previous_run.get("source_state", state)
            result_evaluated_at = previous_run.get("evaluated_at_utc", evaluated_at)
            print(f"Reusing verified Ragas artifact for {state}.", flush=True)
        elif input_hash in result_cache:
            ragas_result, source_state, result_evaluated_at = result_cache[input_hash]
            print(
                f"Reusing {source_state} Ragas result for byte-identical {state} inputs.",
                flush=True,
            )
        else:
            ragas_result = _evaluate(settings, state, answers)
            source_state = state
            result_evaluated_at = evaluated_at
        result_cache[input_hash] = (ragas_result, source_state, result_evaluated_at)
        metrics["ragas"] = ragas_result
        metrics["ragas_run"] = {
            "evaluated_at_utc": result_evaluated_at,
            "evaluator_provider": settings.llm_provider,
            "evaluator_model": settings.model_name,
            "embedding_model": settings.embedding_model,
            "answer_relevancy_strictness": int(
                os.getenv("RAGAS_ANSWER_RELEVANCY_STRICTNESS", "1")
            ),
            "input_sha256": input_hash,
            "source_state": source_state,
            "reused_identical_inputs": source_state != state,
        }
        write_json(metrics_path, metrics)
        updated_metrics[state] = metrics

    comparison = read_json(settings.paths.comparison_metrics)
    for state, metrics in updated_metrics.items():
        comparison[state] = metrics
    comparison["ragas_delta_corrupted_vs_baseline"] = {
        name: round(
            updated_metrics["corrupted"]["ragas"][name]
            - updated_metrics["baseline"]["ragas"][name],
            6,
        )
        for name in RAGAS_METRICS
    }
    comparison["ragas_delta_repaired_vs_corrupted"] = {
        name: round(
            updated_metrics["repaired"]["ragas"][name]
            - updated_metrics["corrupted"]["ragas"][name],
            6,
        )
        for name in RAGAS_METRICS
    }
    write_json(settings.paths.comparison_metrics, comparison)

    phase1_text = settings.paths.baseline_report.read_text(encoding="utf-8")
    ragas_note = ", ".join(
        f"{name}={updated_metrics['baseline']['ragas'][name]:.3f}"
        for name in sorted(RAGAS_METRICS)
    )
    phase1_lines = [
        f"Ragas: {ragas_note}" if line.startswith("Ragas:") else line
        for line in phase1_text.splitlines()
    ]
    write_text(settings.paths.baseline_report, "\n".join(phase1_lines) + "\n")

    quality = comparison["quality"]
    freshness = comparison["freshness"]
    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=updated_metrics["baseline"],
        corrupted_metrics=updated_metrics["corrupted"],
        repaired_metrics=updated_metrics["repaired"],
        baseline_quality=quality["baseline"],
        corrupted_quality=quality["corrupted"],
        repaired_quality=quality["repaired"],
        baseline_freshness=freshness["baseline"],
        corrupted_freshness=freshness["corrupted"],
        repaired_freshness=freshness["repaired"],
    )
    print("Ragas artifacts updated successfully.", flush=True)


if __name__ == "__main__":
    main()
