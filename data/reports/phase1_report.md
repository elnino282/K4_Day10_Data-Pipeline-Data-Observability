# Baseline Pipeline Report

Generated at `2026-08-06T15:46:09.408578+00:00` from the artifacts produced by this run.

## Executive summary

- Source: **Crossref REST API**
- Parsed / cleaned records: **24 / 24**
- Evaluation samples: **24**
- Data quality: **PASS** (13/13 pass)
- Freshness: **FRESH**

## Source lineage and schema

| Item | Runtime value |
|---|---|
| API | `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Requested records | 24 |
| Source snapshot fetched at | `2026-08-06T08:11:57.767481+00:00` |
| Cached snapshot reused | True |
| Raw response | `C:\Users\Quynh Ho\Documents\GitHub\K4_Day10_Data-Pipeline-Data-Observability\data\raw\crossref_response.json` |
| Normalized raw records | `C:\Users\Quynh Ho\Documents\GitHub\K4_Day10_Data-Pipeline-Data-Observability\data\raw\crossref_records.json` |
| Clean schema | `paper_id, title, summary, authors, authors_joined, categories, categories_joined, primary_category, published, updated, age_days, summary_chars, abs_url, pdf_url, comment, text_for_embedding` |

## Retrieval and answer quality

| Metric | Value | Visual |
|---|---:|---|
| `retrieval_hit_rate` | 1.000 | `████████████████████` |
| `mean_token_f1` | 1.000 | `████████████████████` |
| `judge_accuracy` | 1.000 | `████████████████████` |
| `mean_judge_score` | 5.000 | `████████████████████` |

Ragas: answer_relevancy=0.279, context_precision=0.937, context_recall=1.000, faithfulness=1.000

## Data quality checks

| Check | Dimension | Result | Observed | Expectation |
|---|---|:---:|---:|---|
| `required_columns` | schema | ✅ | [] | no required columns are missing |
| `minimum_row_count` | volume | ✅ | 24 | >= 4 rows |
| `paper_id_complete` | completeness | ✅ | 0 | 0 blank IDs |
| `paper_id_unique` | uniqueness | ✅ | 0 | 0 rows with duplicate IDs |
| `title_complete` | completeness | ✅ | 0 | 0 blank titles |
| `title_length` | validity | ✅ | 0.0 | <= 5% titles shorter than 8 chars |
| `summary_complete` | completeness | ✅ | 0.0 | <= 5% blank summaries |
| `summary_length` | validity | ✅ | 0.0 | <= 10% summaries shorter than 40 chars |
| `published_valid` | validity | ✅ | 0 | 0 invalid dates |
| `age_days_valid` | validity | ✅ | 0.0 | <= 5% invalid ages |
| `freshness_ratio` | freshness | ✅ | 0.0 | <= 20% stale rows |
| `embedding_text_complete` | completeness | ✅ | 0.0 | 0 blank embedding texts |
| `summary_chars_consistent` | consistency | ✅ | 0 | 0 inconsistent rows |

## Freshness monitoring

| Signal | Value |
|---|---:|
| Threshold | 180 days |
| Latest publication | 2026-08-01 |
| Oldest publication | 2026-02-12 |
| Stale rows | 0 / 24 |
| Status | **FRESH** |

## Reproducibility and artifacts

The test set contains stable `ground_truth_doc_ids`; later phases reuse this exact file so metric deltas reflect corpus changes rather than evaluation-set drift. The raw API payload, normalized records, clean CSV/JSON, Chroma manifest, answer traces, metrics, validation results and this report are all persisted under `data/`.
