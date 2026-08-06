# Báo cáo nhóm — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
|---|---|
| Khóa/Lớp | K4 |
| Nhóm | K4 Day 10 — Data Pipeline & Observability |
| Repository | [elnino282/K4_Day10_Data-Pipeline-Data-Observability](https://github.com/elnino282/K4_Day10_Data-Pipeline-Data-Observability) |
| Ngày dữ liệu và artifact | 2026-08-06 |
| Ngày kiểm tra báo cáo | 2026-08-06 |

### Thành viên và phạm vi chính

Thông tin dưới đây được đối chiếu từ bốn báo cáo cá nhân trong chính repository.

| STT | Họ và tên | MSSV | Vai trò | Phạm vi/deliverable chính |
|---:|---|---|---|---|
| 1 | Nguyễn Đình Liên Thành | 2A202601790 | Role 1 — Điều phối pipeline | `src/core/`, hai pipeline, entrypoint và release gate |
| 2 | Chu Quang Hiếu | 2A202601344 | Role 2 — Nền tảng dữ liệu & recovery | Crossref ingestion, cleaning, corruption, provenance/recovery |
| 3 | Hồ Ngọc Quỳnh | 2A202601684 | Role 3 — RAG & agent | Embedding adapter, Chroma index, QA, agent và LLM provider |
| 4 | Hoàng Văn Huy | 2A202601356 | Role 4 — Corruption & integration | Corruption flow, repair validation và so sánh ba trạng thái |

## 2. Phạm vi kiểm chứng và kết luận

Báo cáo này chỉ sử dụng ba nguồn bằng chứng có trong repo:

1. mã nguồn hiện tại trong `src/`, `script/` và `tests/`;
2. artifact hiện có trong `data/`;
3. các lệnh test và hai pipeline chạy trực tiếp bằng `.venv` ngày 2026-08-06.

Artifact ghi nhận một pipeline RAG trên 24 bản ghi Crossref với ba trạng thái baseline, corrupted và repaired. Baseline và repaired đều đạt retrieval hit rate `1.000`, mean token F1 `1.000`, judge accuracy `1.000`, mean judge score `5.000`, quality `13/13` và freshness `fresh`. Sau corruption, các chỉ số lần lượt còn `0.500`, `0.491114`, `0.458333`, `2.833333`; quality còn `11/13` và freshness thành `stale_or_invalid`.

Kết quả unit/integration test được chạy lại thực tế:

```text
.................................................                   [100%]
49 passed, 5 subtests passed
```

Pipeline đã được chạy lại theo đúng thứ tự `script/run_phase1.py` rồi `script/run_corruption_flow.py` bằng code hiện tại. Phase 1 sinh báo cáo lúc `2026-08-06T15:46:09.408578Z`; corruption/repair flow sinh báo cáo lúc `2026-08-06T16:16:43.689243Z`. Lượt Phase 1 tái sử dụng raw snapshot đã lưu vì `REFRESH_SOURCE` không bật; không tuyên bố đã gọi mới Crossref trong lượt audit này.

## 3. Kiến trúc và luồng dữ liệu thực tế

```text
Crossref /works
  -> raw response + request metadata + normalized PaperRecord[]
  -> clean DataFrame/CSV/JSON
  -> OpenAI embeddings -> 3 Chroma collections
  -> fixed test set (24 câu)
  -> deterministic metadata QA + LLM/fallback judge
  -> metrics + answer traces + quality/freshness reports
  -> deterministic corruption
  -> rebuild repaired data từ raw records
  -> comparison metrics/report
```

| Khối | Code chính | Artifact chính |
|---|---|---|
| Cấu hình | `src/core/config.py` | `.env.example`, paths dưới `data/` |
| Ingestion | `src/ingestion/crossref.py` | `data/raw/crossref_response.json`, `crossref_request.json`, `crossref_records.json` |
| Cleaning/provenance | `src/ingestion/cleaning.py`, khóa run trong `src/pipelines/phase1.py` | `data/clean/papers_clean.*`, `data/results/baseline_run.json` |
| Retrieval | `src/retrieval/embeddings.py`, `index.py`, `qa.py` | `data/embeddings/*.json`, `data/chroma/` |
| Evaluation | `src/evaluation/testset.py`, `metrics.py` | `data/eval/test_set.json`, `data/results/*metrics.json`, `*answers.json` |
| Observability | `src/observability/quality.py`, `reporting.py` | `data/quality/`, `data/reports/` |
| Orchestration | `src/pipelines/phase1.py`, `corruption_flow.py` | toàn bộ artifact của ba trạng thái |
| UI | `src/webapp/server.py`, `ui/` | giao diện PaperLens đọc artifact thật |

## 4. Nguồn dữ liệu và data contract

### 4.1. Ingestion đã ghi nhận

| Thuộc tính | Giá trị trong artifact |
|---|---|
| Nguồn | Crossref REST API |
| Endpoint | `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Số dòng yêu cầu | 24 |
| HTTP status | 200 |
| API items / usable records | 24 / 24 |
| Thời điểm fetch | `2026-08-06T08:11:57.767481+00:00` |

`fetch_source_records()` cấu hình timeout 30 giây và tối đa 4 lần thử cho lỗi kết nối/timeout hoặc HTTP `429`, `500`, `502`, `503`, `504`. Delay exponential bị giới hạn 8 giây và có đọc `Retry-After`.

### 4.2. Raw và clean dataset

| Signal | Giá trị kiểm tra từ file hiện có |
|---|---:|
| Raw normalized records | 24 |
| Clean baseline rows | 24 |
| Unique `paper_id` | 24 |
| Dòng bị loại trong lượt clean được ghi ở manifest | 0 |
| Khoảng `published` | 2026-02-12 đến 2026-08-01 |
| Khoảng `age_days` | 5 đến 175 |
| Khoảng `summary_chars` | 826 đến 2,601 |
| `categories_joined` rỗng | 24/24 |
| `pdf_url` rỗng | 16/24 |

Clean CSV thực tế có 16 cột:

```text
paper_id, title, summary, authors, authors_joined, categories,
categories_joined, primary_category, published, updated, age_days,
summary_chars, abs_url, pdf_url, comment, text_for_embedding
```

Cleaning chuẩn hóa DOI về lowercase, Unicode NFKC/whitespace, loại record thiếu DOI/title/summary/ngày hợp lệ, deduplicate theo DOI, tính `age_days` và `summary_chars`, rồi ghép các section có nhãn vào `text_for_embedding`. Khi Crossref không có subject, `primary_category` dùng fallback, còn `categories_joined` vẫn có thể rỗng; đây là lý do không được coi 24 category rỗng là 24 record lỗi.

## 5. Embedding, index, QA và provider

| Cấu hình/khả năng | Thực tế trong repo |
|---|---|
| Embedding của artifact | `text-embedding-3-small` |
| Backend | Chroma persistent, cosine |
| Collections | `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Documents mỗi manifest | 24, 24, 24 |
| Retrieval `top_k` | 4 |
| LLM trong `.env` và `baseline_run.json` | `gemini` / `gemini-3.1-flash-lite` |
| Provider code hỗ trợ | OpenAI, Gemini, Anthropic, OpenRouter, Ollama, custom OpenAI-compatible |

Nếu `EMBEDDING_MODEL` bắt đầu bằng `text-embedding-`, code yêu cầu `OPENAI_API_KEY`; tên model khác được xử lý như SentenceTransformer. Vì artifact dùng `text-embedding-3-small`, không nên mô tả lượt bàn giao là MiniLM.

Evaluation không lấy câu trả lời tự do từ agent. `answer_question()` tìm exact title từ câu hỏi, kết hợp semantic search, rồi trích summary/authors/date/category từ metadata của kết quả đầu. LLM được dùng làm judge; nếu provider lỗi, code chuyển sang heuristic token-F1 và ghi rõ fallback trong `judge.reasoning`. Không có marker fallback trong ba file answer hiện tại, nhưng đây vẫn là bằng chứng artifact chứ không phải log độc lập của request Gemini.

## 6. Evaluation set và cách tính metric

`data/eval/test_set.json` có 24 câu lấy từ 6 paper, phân bố đều:

| Question type | Số câu |
|---|---:|
| `summary` | 6 |
| `authors` | 6 |
| `publication_date` | 6 |
| `categories` | 6 |

Mỗi sample có `id`, `question_type`, `question`, `ground_truth` và `ground_truth_doc_ids`. SHA-256 của test set hiện tại là `a25ae6f5570fa94accec413e31aaa425d96534ece7d55f0c26a3562114a13aaf`, đúng với hash trong `comparison_metrics.json`; do đó phép so sánh ba trạng thái dùng cùng evaluation set.

| Metric | Cách tính trong code |
|---|---|
| Retrieval hit rate | Có ít nhất một `ground_truth_doc_id` trong các ID retrieve |
| Token F1 | F1 trên tập token lowercase của reference và prediction |
| Judge accuracy | Tỷ lệ `judge.correct=true` |
| Mean judge score | Trung bình score 1–5 |
| Ragas | Bốn metric chạy bằng `script/run_ragas.py` trên answer trace đã lưu |

Lượt `script/run_ragas.py` trên answer trace mới đã được khởi chạy bằng Gemini `gemini-3.1-flash-lite` và OpenAI `text-embedding-3-small`, nhưng Gemini trả HTTP 429 trước khi hoàn thành mẫu đầu tiên vì quota free-tier theo ngày đã đạt giới hạn 500 request. Vì vậy ba metrics artifact hiện giữ trạng thái `ragas.skipped`; báo cáo không tái sử dụng số Ragas của answer trace cũ và không điền số giả. Cần chạy lại lệnh sau khi quota được cấp lại để có bốn metric Ragas mới.

## 7. Kết quả baseline, corrupted và repaired

| Metric | Baseline | Corrupted | Repaired | Δ corrupted − baseline | Δ repaired − corrupted |
|---|---:|---:|---:|---:|---:|
| Samples | 24 | 24 | 24 | 0 | 0 |
| Retrieval hit rate | 1.000000 | 0.500000 | 1.000000 | -0.500000 | +0.500000 |
| Mean token F1 | 1.000000 | 0.491114 | 1.000000 | -0.508886 | +0.508886 |
| Judge accuracy | 1.000000 | 0.458333 | 1.000000 | -0.541667 | +0.541667 |
| Mean judge score | 5.000 | 2.833333 | 5.000 | -2.166667 | +2.166667 |
| Ragas answer relevancy | n/a | n/a | n/a | n/a | n/a |
| Ragas context precision | n/a | n/a | n/a | n/a | n/a |
| Ragas context recall | n/a | n/a | n/a | n/a | n/a |
| Ragas faithfulness | n/a | n/a | n/a | n/a | n/a |

Đối chiếu answer traces:

| Trạng thái | Answer records | Retrieval hits | Judge correct |
|---|---:|---:|---:|
| Baseline | 24 | 24 | 24 |
| Corrupted | 24 | 12 | 11 |
| Repaired | 24 | 24 | 24 |

Kết luận được artifact hỗ trợ: corruption làm giảm rõ rệt retrieval và chất lượng câu trả lời; rebuild repaired khôi phục các metric về đúng giá trị baseline trên cùng test set.

## 8. Data quality và freshness

Quality hiện dùng 13 kiểm tra khai báo trong code, bao phủ schema, volume, completeness, uniqueness, validity, consistency và freshness. Artifact tự ghi framework là `declarative_quality_checks`; không có bằng chứng để khẳng định Great Expectations đã trực tiếp thực thi các check này.

| Signal | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Quality checks pass | 13/13 | 11/13 | 13/13 |
| Overall quality | pass | fail | pass |
| Check fail | — | `paper_id_unique`, `summary_complete` | — |
| Fresh / stale rows | 24 / 0 | 22 / 2 | 24 / 0 |
| Freshness status | `fresh` | `stale_or_invalid` | `fresh` |
| Oldest publication | 2026-02-12 | 2021-07-02 | 2026-02-12 |
| Latest publication | 2026-08-01 | 2026-07-13 | 2026-08-01 |

Hai cơ chế freshness có ngưỡng khác nhau về ý nghĩa: quality check `freshness_ratio` vẫn pass vì tỷ lệ stale `2/24 = 8.33%` không vượt 20%, trong khi freshness report chỉ đánh dấu `fresh` khi không có dòng stale và không có ngày lỗi. Vì vậy corrupted quality fail do duplicate và blank summary, còn trạng thái freshness fail riêng do 2 dòng stale.

## 9. Corruption và repair

Corruption là deterministic, bắt đầu từ 24 dòng, xóa 2 dòng mới nhất rồi thêm lại 2 duplicate nên vẫn còn 24 dòng nhưng chỉ có 22 DOI duy nhất.

| Scenario | Số dòng/ID bị tác động | Ghi chú |
|---|---:|---|
| `drop_latest_records` | 2 | loại hai paper mới nhất |
| `blank_summary` | 2 | tạo tỷ lệ summary rỗng 8.33% |
| `inject_summary_noise` | 2 | chèn chuỗi noise có nhãn |
| `truncate_title` | 2 | cùng hai ID bị noise |
| `stale_publication_date` | 2 | cùng hai ID bị noise/title truncate, lùi 5 năm |
| `duplicate_rows` | 2 | đưa row count về 24 nhưng unique ID còn 22 |

Repair không sửa trực tiếp corrupted rows. Flow đọc lại `data/raw/crossref_records.json`, chạy cùng cleaning contract/run date rồi so schema, row count, tập DOI và canonical content với baseline. `repair_validation.json` ghi:

- baseline/repaired: 24 dòng và 24 unique ID;
- không có ID thiếu hoặc thừa;
- `document_identity_restored=true`.

## 10. Cách chạy và kết quả test đã xác minh

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".\.venv\Scripts\Activate.ps1"
python -m pytest -q
python script/run_phase1.py
python script/run_corruption_flow.py
python script/run_ui.py
```

Hoặc không activate:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q
```

Kết quả đã xác minh trong lượt audit:

- `python -m pytest -q`: `49 passed, 5 subtests passed`;
- `python script/run_phase1.py`: hoàn tất, sinh `baseline_run.json`, baseline metrics/answers, quality, freshness và report;
- `python script/run_corruption_flow.py`: hoàn tất, sinh lại corrupted/repaired artifacts, `comparison_metrics.json`, `repair_validation.json` và `corruption_report.md`;
- ba answer trace có lần lượt 24/24, 12/24 và 24/24 retrieval hit; không trace nào chứa marker `Fallback heuristic judge`.

Hai pipeline cần `OPENAI_API_KEY` cho `text-embedding-3-small` và credential của evaluator đang cấu hình. Các khóa chỉ được kiểm tra ở dạng có/không, không được in vào log hay báo cáo.

## 11. Giới hạn và sai lệch hiện tại cần công khai

1. **Lượt audit dùng cached raw snapshot.** `crossref_request.json` ghi snapshot được fetch thành công lúc `2026-08-06T08:11:57.767481+00:00`; Phase 1 mới tái sử dụng snapshot này. Vì vậy ingestion/clean/index/evaluation đã chạy end-to-end từ raw artifact, nhưng Crossref không được gọi lại.
2. **Metadata raw còn đường dẫn máy cũ.** Hai trường mô tả artifact trong `crossref_request.json` vẫn chứa prefix `D:\VinUni\...` từ máy tạo snapshot. Pipeline không dùng hai chuỗi này để đọc file và `baseline_run.json` khóa nội dung bằng SHA-256, nhưng provenance nên dùng đường dẫn tương đối để portable hơn.
3. **Evaluation có exact-title lookup.** Câu hỏi chứa nguyên title và QA ưu tiên exact lookup trước semantic results. Vì vậy hit rate baseline `1.0` không đại diện cho một benchmark semantic retrieval thuần túy.
4. **Judge có fallback.** Khi LLM evaluator lỗi, code vẫn tạo judge score bằng heuristic. Ba answer artifact vừa sinh không có marker fallback, nhưng chưa có log request độc lập để audit provider theo từng lời gọi.
5. **Ragas chưa hoàn thành do quota Gemini.** E2E và lượt Ragas đều cấu hình `gemini-3.1-flash-lite`, nhưng lượt Ragas mới bị HTTP 429 do quota 500 request/ngày. Không có `ragas_run` mới; các metric Ragas hiện được trình bày là `n/a`.
6. **Crossref là nguồn sống.** Bật `REFRESH_SOURCE=1` có thể đổi corpus; so sánh chỉ hợp lệ khi khóa cùng raw snapshot, embedding model, `top_k` và test set.
7. **Agent demo là artifact lịch sử độc lập.** `agent_demo_answers.json` vẫn ghi model `gemini-3.5-flash-lite`; file này không được dùng để tính bất kỳ metric E2E nào trong báo cáo và không được đổi nhãn thành 3.1 vì chưa tái sinh thành công bằng model mới.

## 12. Hướng cải thiện có căn cứ

- Thêm run manifest duy nhất chứa commit SHA, Python/package versions, non-secret config, artifact hashes và thời gian chạy.
- Chuyển các đường dẫn trong request metadata sang đường dẫn tương đối và ghi rõ `used_cached_snapshot` trong machine-readable run metadata.
- Tách benchmark semantic-only khỏi exact-title lookup; bổ sung câu hỏi paraphrase và multi-document.
- Ghi rõ judge backend là LLM hay heuristic cho từng sample và tổng hợp fallback count vào metrics.
- Giữ metadata `ragas_run`, input hash và cấu hình timeout/retry khi chạy lại để phân biệt thay đổi evaluator với thay đổi dữ liệu.
- Bổ sung timeout/retry có giới hạn cho LLM judge để lỗi provider không làm một lượt evaluation chờ quá lâu.

## 13. Checklist bàn giao

- [x] Có đủ bốn báo cáo cá nhân theo MSSV và họ tên.
- [x] `group_report.md` dùng số liệu đọc trực tiếp từ artifact.
- [x] Baseline/corrupted/repaired được so trên cùng test-set hash.
- [x] Raw, clean, embedding manifests, eval, answers, metrics, quality và reports đều có artifact.
- [x] Unit/integration tests hiện tại pass: 49 tests và 5 subtests.
- [ ] Ragas đã được khởi chạy nhưng chưa hoàn thành do quota Gemini; cần chạy lại khi quota được cấp lại.
- [x] `baseline_run.json` khóa raw/clean/test-set hash, embedding model, collection, `top_k` và evaluator.
- [x] `comparison_metrics.json` và `repair_validation.json` được sinh lại bởi corruption flow hiện tại.
- [x] Phase 1 và corruption/repair flow đã chạy lại thành công theo revision hiện tại.
