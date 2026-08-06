# Hồ sơ báo cáo của nhóm

Thư mục này chứa báo cáo nhóm và bốn báo cáo cá nhân của repository **K4 Day 10 — Data Pipeline & Data Observability**. Nội dung kỹ thuật và số liệu chính đã được đối chiếu với code/artifact trong repo ngày 2026-08-06; không dùng số liệu giả định.

## 1. Danh mục báo cáo

| Báo cáo | Thành viên/vai trò | Trạng thái |
|---|---|---|
| [`group_report.md`](group_report.md) | Báo cáo chung, kiến trúc, metrics, observability, corruption/repair và giới hạn | Đã hoàn chỉnh |
| [`2A202601790_NguyenDinhLienThanh.md`](2A202601790_NguyenDinhLienThanh.md) | Nguyễn Đình Liên Thành — điều phối pipeline | Có nội dung |
| [`2A202601344_ChuQuangHieu.md`](2A202601344_ChuQuangHieu.md) | Chu Quang Hiếu — nền tảng dữ liệu & recovery | Có nội dung |
| [`2A202601684_HoNgocQuynh.md`](2A202601684_HoNgocQuynh.md) | Hồ Ngọc Quỳnh — RAG & agent | Có nội dung |
| [`2A202601356_HoangVanHuy.md`](2A202601356_HoangVanHuy.md) | Hoàng Văn Huy — corruption & integration | Có nội dung |
| [`individual_report.md`](individual_report.md) | Template gốc | Chỉ là mẫu, không phải bài nộp cá nhân |

Repository được ghi trong báo cáo cá nhân: [elnino282/K4_Day10_Data-Pipeline-Data-Observability](https://github.com/elnino282/K4_Day10_Data-Pipeline-Data-Observability).

## 2. Kết quả đã được đối chiếu

| Signal | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Records | 24 | 24 (22 unique DOI) | 24 |
| Retrieval hit rate | 1.000 | 0.500 | 1.000 |
| Mean token F1 | 1.000 | 0.491114 | 1.000 |
| Judge accuracy | 1.000 | 0.458333 | 1.000 |
| Mean judge score | 5.000 | 2.833333 | 5.000 |
| Ragas answer relevancy | n/a | n/a | n/a |
| Ragas context precision | n/a | n/a | n/a |
| Ragas context recall | n/a | n/a | n/a |
| Ragas faithfulness | n/a | n/a | n/a |
| Quality checks | 13/13 | 11/13 | 13/13 |
| Freshness | `fresh` | `stale_or_invalid` | `fresh` |

Nguồn số liệu: `data/results/*metrics.json`, `data/results/*answers.json`, `data/quality/*.json` và `data/results/corruption_log.json`. Lượt Ragas mới bị Gemini trả HTTP 429 vì quota free-tier 500 request/ngày đã hết trước khi hoàn thành mẫu đầu tiên; do đó metrics hiện ghi `ragas.skipped` và báo cáo để `n/a`, không dùng lại số của answer trace cũ.

Test được chạy trực tiếp bằng môi trường `.venv`:

```text
49 passed, 5 subtests passed
```

## 3. Bản đồ bằng chứng

| Nội dung cần kiểm tra | Source of truth |
|---|---|
| Request Crossref, query/filter, số record | `data/raw/crossref_request.json` |
| Raw API response và normalized records | `data/raw/crossref_response.json`, `crossref_records.json` |
| Clean schema/data | `data/clean/papers_clean.csv`, `papers_clean.json` |
| Embedding model, collection, indexed documents | `data/embeddings/*.json` |
| Test set và ground-truth IDs | `data/eval/test_set.json` |
| Ba bộ metrics và answer trace | `data/results/` |
| Quality/freshness | `data/quality/` |
| Corruption scenario và affected IDs | `data/results/corruption_log.json` |
| So sánh machine-readable | `data/results/comparison_metrics.json` |
| Repair identity validation | `data/results/repair_validation.json` |
| Báo cáo do pipeline sinh | `data/reports/phase1_report.md`, `corruption_report.md` |
| Yêu cầu chấm điểm | `Rubric.md` ở root repo |

Không lấy số từ README hoặc báo cáo cá nhân khi có JSON machine-readable tương ứng; JSON trong `data/` được ưu tiên làm nguồn đối chiếu.

## 4. Cách kiểm tra nhanh

Trong PowerShell tại root repo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".\.venv\Scripts\Activate.ps1"
python -m pytest -q
```

Không cần activate nếu gọi interpreter trực tiếp:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q
```

Các lệnh pipeline theo code hiện tại:

```powershell
python script/run_phase1.py
python script/run_corruption_flow.py
python script/run_ragas.py
python script/run_ui.py
```

`run_phase1.py` dùng raw snapshot hiện có khi đủ ba raw artifact và `REFRESH_SOURCE` không bật, nhưng vẫn rebuild embedding/evaluation. Với cấu hình artifact hiện tại (`text-embedding-3-small` và Gemini judge), bước này cần credential/provider khả dụng và có thể phát sinh API usage.

## 5. Lưu ý tái lập quan trọng

Checkout hiện tại đã có `data/results/baseline_run.json`, được Phase 1 sinh lại ngày 2026-08-06. File khóa SHA-256 của raw response, raw records, clean JSON và test set, cùng embedding model, collection, `top_k`, evaluator provider/model.

Thứ tự tái lập đúng vẫn là:

1. cấu hình credential không đưa vào Git;
2. chạy `python script/run_phase1.py` để tạo baseline mới và `baseline_run.json`;
3. kiểm tra phase 1 artifacts;
4. chạy `python script/run_corruption_flow.py`;
5. chạy test và đối chiếu lại report với JSON mới.

Revision hiện tại đã được chạy lại theo thứ tự trên. Lượt Phase 1 dùng raw snapshot đã lưu vì `REFRESH_SOURCE` không bật; không được diễn giải thành một lần fetch Crossref mới. Corruption flow đã tái sinh cả `comparison_metrics.json`, `repair_validation.json` và báo cáo Markdown.

## 6. Quy tắc cập nhật báo cáo

Khi chạy lại pipeline, chỉ cập nhật số liệu sau khi:

- file JSON parse được và không rỗng;
- ba trạng thái dùng cùng `data/eval/test_set.json`/SHA-256;
- baseline artifact không bị corruption flow ghi đè;
- số pass/fail quality khớp danh sách check;
- freshness khớp `fresh_rows`, `stale_rows` và `status`;
- Ragas chỉ được báo cáo nếu output không phải `skipped` hoặc `error`;
- kết quả pytest được lấy từ lệnh vừa chạy, không sao chép từ báo cáo cũ.

Không commit `.env`, API key, token hoặc log chứa secret. `.env.example` mới là file cấu hình mẫu được phép chia sẻ.

## 7. Checklist trước khi nộp

- [x] Có một báo cáo nhóm và bốn báo cáo cá nhân có tên/MSSV cụ thể.
- [x] Báo cáo nhóm liên kết kết luận với artifact thực tế.
- [x] Metrics, quality và freshness khớp JSON hiện có.
- [x] Test hiện tại pass: 49 tests, 5 subtests.
- [ ] Ragas đã được khởi chạy nhưng chưa hoàn thành do quota Gemini; cần chạy lại khi quota được cấp lại.
- [x] Có `baseline_run.json`, `comparison_metrics.json` và `repair_validation.json` từ pipeline hiện tại.
- [x] Đã chạy lại Phase 1 và corruption/repair flow theo đúng thứ tự.
