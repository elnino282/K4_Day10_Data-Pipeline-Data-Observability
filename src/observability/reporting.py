from __future__ import annotations

from typing import Any

from core.utils import write_text


def _value(payload: dict[str, Any], key: str, default: Any = "n/a") -> Any:
    return payload.get(key, default) if isinstance(payload, dict) else default


def _metric_lines(metrics: dict[str, Any]) -> list[str]:
    keys = ["samples", "retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]
    return [f"- `{key}`: {_value(metrics, key)}" for key in keys]


def _quality_lines(quality: dict[str, Any]) -> list[str]:
    summary = _value(quality, "summary", {})
    lines = [
        f"- `state`: {_value(quality, 'state')}",
        f"- `passed`: {_value(quality, 'passed')}",
        f"- `input_rows`: {_value(quality, 'input_rows')}",
    ]
    if isinstance(summary, dict):
        for key, value in summary.items():
            lines.append(f"- `{key}`: {value}")
    return lines


def _freshness_lines(freshness: dict[str, Any]) -> list[str]:
    keys = [
        "status",
        "is_fresh",
        "latest_published",
        "oldest_published",
        "stale_rows",
        "total_rows",
        "freshness_threshold_days",
    ]
    return [f"- `{key}`: {_value(freshness, key)}" for key in keys]


def _delta(after: dict[str, Any], before: dict[str, Any], key: str) -> str:
    try:
        return f"{float(_value(after, key)) - float(_value(before, key)):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a baseline markdown report from real artifact payloads."""
    source_lines = [f"- `{key}`: {value}" for key, value in source_summary.items()]
    ragas = _value(metrics, "ragas", {})
    ragas_line = ragas if isinstance(ragas, str) else ", ".join(f"{key}: {value}" for key, value in ragas.items())
    text = "\n".join(
        [
            "# Phase 1 Baseline Report",
            "",
            "## Source",
            *source_lines,
            "",
            "## Evaluation Metrics",
            *_metric_lines(metrics),
            f"- `ragas`: {ragas_line}",
            "",
            "## Data Quality",
            *_quality_lines(quality),
            "",
            "## Freshness",
            *_freshness_lines(freshness),
            "",
        ]
    )
    write_text(report_path, text)


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write a markdown comparison report for baseline, corrupted, and repaired states."""
    metric_keys = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]
    table = [
        "| Metric | Baseline | Corrupted | Repaired | Corrupted delta | Repaired delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in metric_keys:
        table.append(
            "| "
            f"`{key}` | {_value(baseline_metrics, key)} | {_value(corrupted_metrics, key)} | "
            f"{_value(repaired_metrics, key)} | {_delta(corrupted_metrics, baseline_metrics, key)} | "
            f"{_delta(repaired_metrics, baseline_metrics, key)} |"
        )

    text = "\n".join(
        [
            "# Corruption And Repair Report",
            "",
            "## Metric Comparison",
            *table,
            "",
            "## Corrupted Quality",
            *_quality_lines(corrupted_quality),
            "",
            "## Corrupted Freshness",
            *_freshness_lines(corrupted_freshness),
            "",
            "## Repaired Quality",
            *_quality_lines(repaired_quality),
            "",
            "## Repaired Freshness",
            *_freshness_lines(repaired_freshness),
            "",
            "## Notes",
            "- Conclusions should be checked against the answers and quality artifacts before demo.",
            "- If judge fallback or Ragas errors occurred, treat those metrics as limited evidence.",
            "",
        ]
    )
    write_text(report_path, text)
