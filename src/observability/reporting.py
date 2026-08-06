from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.utils import write_text


def _metric(value: Any, digits: int = 3) -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value if value is not None else "n/a")


def _quality_summary(quality: dict[str, Any] | None) -> str:
    if not quality:
        return "n/a"
    stats = quality.get("statistics", {})
    return f"{stats.get('successful_checks', 0)}/{stats.get('evaluated_checks', 0)} pass"


def _bar(value: Any, scale: float = 1.0, width: int = 20) -> str:
    try:
        normalized = max(0.0, min(1.0, float(value) / scale))
    except (TypeError, ValueError):
        normalized = 0.0
    filled = round(normalized * width)
    return "█" * filled + "░" * (width - filled)


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a baseline report whose claims are derived from runtime artifacts."""
    checks = quality.get("checks", [])
    check_rows = "\n".join(
        f"| `{item.get('name')}` | {item.get('dimension')} | {'✅' if item.get('success') else '❌'} | "
        f"{item.get('observed')} | {item.get('expectation')} |"
        for item in checks
    ) or "| _No checks_ | - | ❌ | - | - |"
    ragas = metrics.get("ragas", {})
    ragas_note = ragas.get("skipped") or ragas.get("error") or ", ".join(
        f"{key}={_metric(value)}" for key, value in ragas.items()
    )
    generated_at = datetime.now(UTC).isoformat()
    text = f"""# Baseline Pipeline Report

Generated at `{generated_at}` from the artifacts produced by this run.

## Executive summary

- Source: **{source_summary.get('source', 'Crossref REST API')}**
- Parsed / cleaned records: **{source_summary.get('raw_record_count', 'n/a')} / {source_summary.get('clean_record_count', 'n/a')}**
- Evaluation samples: **{metrics.get('samples', 0)}**
- Data quality: **{'PASS' if quality.get('overall_success') else 'FAIL'}** ({_quality_summary(quality)})
- Freshness: **{str(freshness.get('status', 'unknown')).upper()}**

## Source lineage and schema

| Item | Runtime value |
|---|---|
| API | `{source_summary.get('api_url', 'https://api.crossref.org/works')}` |
| Query | `{source_summary.get('query', '')}` |
| Filter | `{source_summary.get('filter', '')}` |
| Max requested | {source_summary.get('max_results', 'n/a')} |
| Raw response | `{source_summary.get('raw_response_path', '')}` |
| Normalized raw records | `{source_summary.get('raw_records_path', '')}` |
| Clean schema | `{', '.join(source_summary.get('clean_schema', []))}` |

## Retrieval and answer quality

| Metric | Value | Visual |
|---|---:|---|
| `retrieval_hit_rate` | {_metric(metrics.get('retrieval_hit_rate'))} | `{_bar(metrics.get('retrieval_hit_rate'))}` |
| `mean_token_f1` | {_metric(metrics.get('mean_token_f1'))} | `{_bar(metrics.get('mean_token_f1'))}` |
| `judge_accuracy` | {_metric(metrics.get('judge_accuracy'))} | `{_bar(metrics.get('judge_accuracy'))}` |
| `mean_judge_score` | {_metric(metrics.get('mean_judge_score'))} | `{_bar(metrics.get('mean_judge_score'), scale=5.0)}` |

Ragas: {ragas_note}

## Data quality checks

| Check | Dimension | Result | Observed | Expectation |
|---|---|:---:|---:|---|
{check_rows}

## Freshness monitoring

| Signal | Value |
|---|---:|
| Threshold | {freshness.get('threshold_days', 'n/a')} days |
| Latest publication | {freshness.get('latest_published', 'n/a')} |
| Oldest publication | {freshness.get('oldest_published', 'n/a')} |
| Stale rows | {freshness.get('stale_rows', 'n/a')} / {freshness.get('total_rows', 'n/a')} |
| Status | **{str(freshness.get('status', 'unknown')).upper()}** |

## Reproducibility and artifacts

The test set contains stable `ground_truth_doc_ids`; later phases reuse this exact file so metric deltas reflect corpus changes rather than evaluation-set drift. The raw API payload, normalized records, clean CSV/JSON, Chroma manifest, answer traces, metrics, validation results and this report are all persisted under `data/`.
"""
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
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
) -> None:
    """Write a three-state comparison with explicit deltas and causal evidence."""
    metric_names = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]
    rows: list[str] = []
    for name in metric_names:
        baseline = baseline_metrics.get(name)
        corrupted = corrupted_metrics.get(name)
        repaired = repaired_metrics.get(name)
        corrupted_delta = float(corrupted) - float(baseline) if isinstance(baseline, (int, float)) and isinstance(corrupted, (int, float)) else None
        repaired_delta = float(repaired) - float(corrupted) if isinstance(corrupted, (int, float)) and isinstance(repaired, (int, float)) else None
        rows.append(
            f"| `{name}` | {_metric(baseline)} | {_metric(corrupted)} | {_metric(repaired)} | "
            f"{_metric(corrupted_delta)} | {_metric(repaired_delta)} |"
        )

    baseline_hit = float(baseline_metrics.get("retrieval_hit_rate", 0.0))
    corrupted_hit = float(corrupted_metrics.get("retrieval_hit_rate", 0.0))
    repaired_hit = float(repaired_metrics.get("retrieval_hit_rate", 0.0))
    baseline_f1 = float(baseline_metrics.get("mean_token_f1", 0.0))
    corrupted_f1 = float(corrupted_metrics.get("mean_token_f1", 0.0))
    repaired_f1 = float(repaired_metrics.get("mean_token_f1", 0.0))
    recovery = "confirmed" if repaired_hit >= baseline_hit - 0.01 and repaired_f1 >= baseline_f1 - 0.01 else "partial"
    text = f"""# Corruption, Repair and RAG Impact Report

Generated at `{datetime.now(UTC).isoformat()}`. All three states use the same persisted evaluation set.

## Executive conclusion

Corruption changed retrieval hit rate by **{corrupted_hit - baseline_hit:+.3f}** and token F1 by **{corrupted_f1 - baseline_f1:+.3f}**. Repair then changed them by **{repaired_hit - corrupted_hit:+.3f}** and **{repaired_f1 - corrupted_f1:+.3f}**, respectively. Recovery is **{recovery.upper()}** relative to baseline.

## Metric comparison

| Metric | Baseline | Corrupted | Repaired | Δ corrupt vs base | Δ repair vs corrupt |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

### Retrieval hit-rate visualization

```text
Baseline  {_bar(baseline_hit)} {_metric(baseline_hit)}
Corrupted {_bar(corrupted_hit)} {_metric(corrupted_hit)}
Repaired  {_bar(repaired_hit)} {_metric(repaired_hit)}
```

## Observability signals

| Signal | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Quality checks | {_quality_summary(baseline_quality)} | {_quality_summary(corrupted_quality)} | {_quality_summary(repaired_quality)} |
| Quality status | {_metric(baseline_quality.get('overall_success') if baseline_quality else None)} | {_metric(corrupted_quality.get('overall_success'))} | {_metric(repaired_quality.get('overall_success'))} |
| Freshness status | {(baseline_freshness or {}).get('status', 'n/a')} | {corrupted_freshness.get('status', 'n/a')} | {repaired_freshness.get('status', 'n/a')} |
| Stale rows | {(baseline_freshness or {}).get('stale_rows', 'n/a')} | {corrupted_freshness.get('stale_rows', 'n/a')} | {repaired_freshness.get('stale_rows', 'n/a')} |

## Causal interpretation

1. Dropped recent papers remove ground-truth document IDs from the index, directly lowering retrieval hit rate.
2. Blank/noisy summaries and truncated titles weaken semantic evidence and factual extraction, lowering token F1 and judge results.
3. Stale dates and duplicate IDs are independently detected by freshness, validity and uniqueness checks before relying only on end-user failures.
4. Repair rebuilds the clean dataset from the immutable normalized raw snapshot, then rebuilds a separate Chroma collection. A return toward baseline metrics on the unchanged test set is evidence of recovery.

## Reproduction

```powershell
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

See `data/results/corruption_log.json` for affected IDs and `data/results/comparison_metrics.json` for the machine-readable comparison.
"""
    write_text(report_path, text)
