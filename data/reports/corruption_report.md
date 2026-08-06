# Corruption, Repair and RAG Impact Report

Generated at `2026-08-06T17:57:10.089781+00:00`. All three states use the same persisted evaluation set.

## Executive conclusion

Corruption changed retrieval hit rate by **-0.500** and token F1 by **-0.509**. Repair then changed them by **+0.500** and **+0.509**, respectively. Recovery is **CONFIRMED** relative to baseline.

## Metric comparison

| Metric | Baseline | Corrupted | Repaired | Δ corrupt vs base | Δ repair vs corrupt |
|---|---:|---:|---:|---:|---:|
| `retrieval_hit_rate` | 1.000 | 0.500 | 1.000 | -0.500 | 0.500 |
| `mean_token_f1` | 1.000 | 0.491 | 1.000 | -0.509 | 0.509 |
| `judge_accuracy` | 1.000 | 0.458 | 1.000 | -0.542 | 0.542 |
| `mean_judge_score` | 5.000 | 2.833 | 5.000 | -2.167 | 2.167 |
| `ragas.answer_relevancy` | 0.279 | 0.229 | 0.279 | -0.050 | 0.050 |
| `ragas.context_precision` | 0.937 | 0.464 | 0.937 | -0.473 | 0.473 |
| `ragas.context_recall` | 1.000 | 0.375 | 1.000 | -0.625 | 0.625 |
| `ragas.faithfulness` | 1.000 | 0.549 | 1.000 | -0.451 | 0.451 |

### Retrieval hit-rate visualization

```text
Baseline  ████████████████████ 1.000
Corrupted ██████████░░░░░░░░░░ 0.500
Repaired  ████████████████████ 1.000
```

## Observability signals

| Signal | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Quality checks | 13/13 pass | 11/13 pass | 13/13 pass |
| Quality status | pass | fail | pass |
| Freshness status | fresh | stale_or_invalid | fresh |
| Stale rows | 0 | 2 | 0 |

## Causal interpretation

1. Dropped recent papers remove ground-truth document IDs from the index, directly lowering retrieval hit rate.
2. Blank/noisy summaries and truncated titles weaken semantic evidence and factual extraction, lowering token F1 and judge results.
3. Stale dates and duplicate IDs are independently detected by freshness, validity and uniqueness checks before relying only on end-user failures.
4. Repair rebuilds the clean dataset from the immutable normalized raw snapshot, then rebuilds a separate Chroma collection. A return toward baseline metrics on the unchanged test set is evidence of recovery.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m pipelines.phase1
.\.venv\Scripts\python.exe -m pipelines.corruption_flow
```

See `data/results/corruption_log.json` for affected IDs and `data/results/comparison_metrics.json` for the machine-readable comparison.
