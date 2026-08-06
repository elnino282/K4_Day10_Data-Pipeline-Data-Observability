# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
|---|---|
| Khóa/Lớp | K4 |
| Tên nhóm | K4 Day 10 — Data Pipeline & Observability |
| Repository | `K4_Day10_Data-Pipeline-Data-Observability` |
| Ngày hoàn thành kỹ thuật | 2026-08-06 |

> Nhóm cần thay thông tin hành chính dưới đây bằng họ tên và MSSV thật trước khi nộp. Không suy đoán thông tin cá nhân trong báo cáo kỹ thuật.

### Thành viên và phân công

| STT | Thành viên | MSSV | Vai trò chính | Module/deliverable sở hữu |
|---:|---|---|---|---|
| 1 | Thành viên 1 — cần bổ sung tên | Cần bổ sung | Source owner | `crossref.py`, raw response/records |
| 2 | Thành viên 2 — cần bổ sung tên | Cần bổ sung | Data model & test-set owner | `cleaning.py`, `testset.py`, clean/eval artifacts |
| 3 | Thành viên 3 — cần bổ sung tên | Cần bổ sung | Observability owner | `quality.py`, `reporting.py`, quality/freshness reports |
| 4 | Thành viên 4 — cần bổ sung tên | Cần bổ sung | Integration & corruption owner | `corruption.py`, hai pipeline, comparison artifacts |

## 2. Tóm tắt kết quả

Project đã hoàn thành hai pipeline end-to-end trên 24 công bố học thuật lấy trực tiếp từ Crossref. Baseline lưu raw response và normalized records, tạo clean CSV/JSON, OpenAI embeddings, ba Chroma collection tách biệt, test set 24 câu, answer traces, metrics, quality/freshness validations và Markdown report. Baseline đạt retrieval hit rate, token F1 và judge accuracy đều `1.000`; mean judge score `5.000`; 13/13 quality checks pass và freshness là `fresh`.

Flow thứ hai áp dụng sáu corruption scenario có log document ID: xóa bản ghi mới nhất, blank/noise summary, truncate title, stale date và duplicate. Retrieval hit rate giảm còn `0.500`, token F1 còn `0.491`, judge accuracy còn `0.458`; quality giảm còn 11/13 và freshness chuyển sang `stale_or_invalid`. Repair không vá trực tiếp corrupted rows mà rebuild từ normalized raw snapshot, phục hồi đủ 24 document IDs, 13/13 checks, freshness `fresh` và toàn bộ agent metrics về baseline. Giới hạn hiện tại là Ragas để opt-in nhằm tránh chi phí/thời gian API ngoài ý muốn; bốn metrics bắt buộc và provider-backed Gemini judge đã chạy thật.

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref REST API
  -> raw API payload + normalized PaperRecord snapshot
  -> canonical clean dataframe + freshness fields
  -> OpenAI embeddings + ChromaDB
  -> fixed 24-question evaluation set
  -> deterministic corpus QA + Gemini judge
  -> quality/freshness artifacts + baseline report
  -> deterministic corruption + isolated Chroma collection
  -> repair from immutable raw snapshot + isolated collection
  -> machine-readable comparison + Markdown visualization
```

| Khối | Input | Xử lý chính | Output/artifact |
|---|---|---|---|
| Ingestion | Crossref `/works` | Query/filter, timeout, retry/backoff, parse JATS/DOI/date | `data/raw/crossref_response.json`, `crossref_records.json` |
| Cleaning | `PaperRecord[]` | NFKC/whitespace, validation, dedup, age, embedding text | `data/clean/papers_clean.*` |
| Embedding/index | Clean dataframe | `text-embedding-3-small`, cosine Chroma collections | `data/embeddings/*.json`, local `data/chroma/` |
| Evaluation | Fixed test set + index | Retrieval hit, token F1, Gemini judge, optional Ragas | `data/results/*metrics.json`, `*answers.json` |
| Observability | Dataframe | 13 checks across schema/volume/completeness/uniqueness/validity/consistency/freshness | `data/quality/` |
| Corruption/repair | Baseline clean + raw snapshot | Six deterministic scenarios; rebuild clean data from raw | corrupted/repaired datasets and log |
| Orchestration | Settings + artifacts | Baseline and corruption/repair CLI flows | `data/reports/*.md` |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | `gemini` / `gemini-3.5-flash-lite` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` |
| Crossref records | 24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Corruption | deterministic, không dùng random seed |
| Ragas | opt-in bằng `RUN_RAGAS=1`; lượt bàn giao để tắt |

```powershell
uv sync
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run pytest -q
```

| Lệnh | Trạng thái | Lần chạy xác minh | Bằng chứng |
|---|---|---|---|
| Baseline pipeline | Thành công | 2026-08-06 | `baseline_metrics.json`, `phase1_report.md` |
| Corruption flow | Thành công | 2026-08-06 | `comparison_metrics.json`, `corruption_report.md` |
| Unit tests | 25 passed | 2026-08-06 | `tests/` và output pytest |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Source | `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Số record requested / usable | 24 / 24 |
| Retry | Tối đa 4 lần cho connection/timeout và HTTP 429/5xx; exponential backoff tối đa 8 giây, tôn trọng `Retry-After` |

### Schema và quy tắc

| Trường | Kiểu | Bắt buộc | Xử lý |
|---|---|:---:|---|
| `paper_id` | string DOI lowercase | Có | Bỏ record rỗng, dedup theo ID |
| `title` | string | Có | Strip markup, NFKC/whitespace, tối thiểu 5 ký tự |
| `summary` | string | Có | Decode HTML/JATS, tối thiểu 40 ký tự |
| `authors`, `categories` | list[string] | Không | Normalize, loại trùng, tạo các cột `_joined` |
| `published`, `updated` | ISO date/datetime | published có | Parse UTC; record không có published hợp lệ bị loại |
| `age_days` | integer | Có | Chênh lệch ngày chạy UTC và `published` |
| `text_for_embedding` | string | Có | Ghép nhãn Title, Abstract, Authors, Topics, Published |

Lượt dữ liệu thực tế có 24 raw records và 24 clean records; không record nào bị loại ở baseline. Document identity luôn là DOI, không phụ thuộc vị trí dòng nên ground truth giữ ổn định qua rebuild.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
|---|---|
| Số câu hỏi | 24 (6 paper gần nhất × 4 loại) |
| `question_type` | `summary`, `authors`, `publication_date`, `categories` |
| Ground truth ID | DOI trong `ground_truth_doc_ids` |
| Embedding/vector store | `text-embedding-3-small`, Chroma cosine |
| Collections | `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| LLM judge | Gemini, structured score 1–5/correct/reasoning; deterministic fallback nếu provider lỗi |
| Shared test set | `data/eval/test_set.json`, SHA-256 `a25ae6f5570fa94accec413e31aaa425d96534ece7d55f0c26a3562114a13aaf` |

Test set không được tái sinh trong corruption flow. Nhờ vậy, metric delta đo thay đổi ở corpus/index thay vì thay đổi độ khó câu hỏi.

## 7. Kết quả baseline và artifact checklist

| Artifact | Đường dẫn | Trạng thái |
|---|---|:---:|
| Raw response/records | `data/raw/` | Có |
| Cleaned CSV/JSON | `data/clean/papers_clean.*` | Có |
| Embedding manifest | `data/embeddings/papers_embeddings.json` | Có |
| Evaluation set | `data/eval/test_set.json` | Có |
| Metrics/answers | `data/results/baseline_*` | Có |
| Quality/freshness | `data/quality/` | Có |
| Baseline report | `data/reports/phase1_report.md` | Có |
| LLM agent demo | `data/results/agent_demo_answers.json` | Có, Gemini success |

| Metric | Baseline | Diễn giải |
|---|---:|---|
| `retrieval_hit_rate` | 1.000 | Mọi câu đều retrieve đúng DOI ground truth trong top-k |
| `mean_token_f1` | 1.000 | Factual QA khớp ground truth của clean corpus |
| `judge_accuracy` | 1.000 | Tất cả câu được judge đúng |
| `mean_judge_score` | 5.000 | Điểm trung bình tối đa |
| Ragas | skipped (opt-in) | Không chạy để kiểm soát API cost; lý do được ghi trong metrics |

## 8. Data quality và freshness

Baseline pass 13/13 checks. Các check bao phủ required columns, minimum row count, ID/title/summary completeness, ID uniqueness, title/summary length, valid published/age, stale ratio, embedding-text completeness và `summary_chars` consistency. Bằng chứng: `data/quality/baseline_quality.json` và validation-shaped artifact trong `data/quality/gx/`.

| Signal | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Quality checks | 13/13 pass | 11/13 pass | 13/13 pass |
| Freshness | fresh | stale_or_invalid | fresh |
| Stale rows | 0 | 2 | 0 |
| Latest / oldest baseline | 2026-08-01 / 2026-02-12 | — | phục hồi như baseline |

## 9. Corruption scenarios và repair

| Scenario | Cách tạo | Số ID | Signal/tác động |
|---|---|---:|---|
| Drop latest | Xóa 2 paper mới nhất | 2 | Ground-truth IDs biến mất, retrieval giảm |
| Blank summary | Đặt summary rỗng | 2 | Summary completeness/length fail |
| Summary noise | Prefix noise có chủ đích | 2 | Answer evidence sai, token F1/judge giảm |
| Truncate title | Cắt title còn 8–18 ký tự | 2 | Exact title lookup và semantic signal yếu |
| Stale date | Lùi ngày 5 năm, tăng age 1,826 ngày | 2 | Freshness chuyển stale |
| Duplicate rows | Nhân đôi 2 dòng | 2 | ID uniqueness fail |

Toàn bộ affected IDs có trong `data/results/corruption_log.json`. Repair đọc lại `crossref_records.json`, chạy cùng cleaning contract và rebuild collection mới. `repair_validation.json` xác nhận không thiếu/thừa ID và `document_identity_restored=true`, vì vậy repair dựa trên nguồn raw đáng tin cậy chứ không che lỗi ở output.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Δ corruption | Δ repair |
|---|---:|---:|---:|---:|---:|
| `retrieval_hit_rate` | 1.000 | 0.500 | 1.000 | -0.500 | +0.500 |
| `mean_token_f1` | 1.000 | 0.491 | 1.000 | -0.509 | +0.509 |
| `judge_accuracy` | 1.000 | 0.458 | 1.000 | -0.542 | +0.542 |
| `mean_judge_score` | 5.000 | 2.875 | 5.000 | -2.125 | +2.125 |
| Quality checks | 13/13 pass | 11/13 fail | 13/13 pass | -2 checks | +2 checks |
| Freshness | fresh | stale_or_invalid | fresh | degraded | restored |

Hai chuỗi nguyên nhân–bằng chứng:

1. Drop/latest + title/summary corruption → uniqueness/completeness/freshness báo lỗi → retrieval giảm 50 điểm phần trăm và token F1 giảm 0.509.
2. Rebuild từ normalized raw snapshot → đủ 24 IDs, quality/freshness phục hồi → cả bốn agent metrics trở lại đúng baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** baseline retrieval hit là 1.0 nhưng token F1 ban đầu chỉ 0.75 ở nhóm câu category.
- **Nguyên nhân gốc:** cleaning dùng `primary_category=uncategorized` khi Crossref thiếu subject, nhưng index metadata chỉ giữ `categories_joined`; QA vì thế trả chuỗi rỗng dù retrieve đúng document.
- **Cách xử lý:** thêm `primary_category` vào metadata contract và fallback trong category answer extraction.
- **Xác minh:** thêm regression test; pytest tăng lên 25 pass; chạy lại baseline cho token F1 1.0 và không còn answer trace lệch ground truth.

## 12. Giới hạn và hướng cải thiện

| Giới hạn | Ảnh hưởng | Cải thiện có thể kiểm chứng |
|---|---|---|
| Ragas mặc định tắt | Chưa có bốn Ragas submetrics trong lượt bàn giao | Chạy `RUN_RAGAS=1` trong môi trường có ngân sách, lưu cost/runtime và so sánh ba trạng thái |
| Crossref là nguồn live | Snapshot mới có thể đổi paper và metric | Pin raw snapshot/version/hash cho mỗi lần nộp |
| Test set sinh theo template metadata | Chưa đánh giá câu hỏi tổng hợp nhiều paper | Thêm human-reviewed multi-document samples, đo riêng theo question type |

## 13. Checklist trước khi nộp

- [ ] Đã bổ sung họ tên, MSSV, tên nhóm/repository URL thật và báo cáo cá nhân.
- [x] Hai lệnh pipeline đã chạy end-to-end trên phiên bản bàn giao.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set/hash.
- [x] Metrics trong báo cáo khớp `data/results/`.
- [x] Quality/freshness conclusions khớp `data/quality/`.
- [x] Raw, clean, embeddings, eval, answers, metrics và reports đều có artifact.
- [x] Có test/validation bổ sung (`25 passed`).
- [x] Không ghi API key/token trong source, report hoặc log.
