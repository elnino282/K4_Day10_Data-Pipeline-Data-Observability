# Vai trò 2 — Nền tảng dữ liệu & recovery

## Phạm vi

Vai trò 2 sở hữu `src/ingestion/`, `data/raw/`, `data/clean/` và `data/results/corruption_log.json`; phối hợp phần corruption/rebuild trong `src/pipelines/corruption_flow.py` với Vai trò 1. Không sở hữu index, evaluation, observability hoặc orchestration end-to-end.

## Contract dữ liệu và artifact

`PaperRecord` là bản ghi nguồn: `paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment`.

Clean contract bắt buộc: `paper_id`, `title`, `summary`, `published`, `authors_joined`, `categories_joined`, `abs_url`, `pdf_url`, `text_for_embedding`, `age_days`, `summary_chars`. `paper_id` là khóa ổn định; `text_for_embedding` được tạo deterministically từ nội dung canonical đã clean.

| Trạng thái | Artifact theo `src/core/config.py` |
| --- | --- |
| Raw snapshot | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` |
| Baseline clean | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` |
| Corrupted clean | `data/clean/papers_clean_corrupted.csv`, `data/clean/papers_clean_corrupted.json` |
| Repaired clean | `data/clean/papers_clean_repaired.csv`, `data/clean/papers_clean_repaired.json` |
| Corruption log | `data/results/corruption_log.json` |

Không ghi secret. Không sửa tay dữ liệu corrupted và không copy baseline giả repaired.

## Kế hoạch phối hợp

### 00:00–00:30 — Chốt nguồn/model
- [ ] Xác minh endpoint/query/filter Crossref với Vai trò 1.
- [ ] Chốt mapping payload sang `PaperRecord`, quy tắc `paper_id`, run date, sort và deduplicate.

### 00:30–01:05 — Fetch/load và snapshot
- [ ] Fetch/load Crossref trong `src/ingestion/crossref.py`; lưu raw HTTP payload và `PaperRecord` snapshot.
- [ ] Dùng retry/backoff có giới hạn cho lỗi tạm thời (đặc biệt 429/503), log lỗi cuối không kèm credential.

### 01:05–01:35 — Cleaning truy vết
- [ ] Chuẩn hóa và ghi/return record vào, record loại, lý do loại, rule normalize, duplicate key.
- [ ] Tạo clean contract deterministically; xuất CSV/JSON cùng schema và cùng tập `paper_id`.

### 01:35–02:00 — Handoff/baseline freeze
- [ ] Gửi schema, row count, tập/hash `paper_id`, run date và path baseline clean.
- [ ] Freeze baseline từ một raw snapshot xác định trước khi build index/evaluation; chỉ refresh khi được chốt rõ ràng.

### 02:00–02:15 — Corruption
- [ ] Chốt seed, loại corruption, tỷ lệ/target và format `corruption_log.json` với Vai trò 1.
- [ ] Bảo đảm mutation deterministic, logged và baseline nguyên vẹn.

### 02:15–03:15 — Recovery
- [ ] Tạo corrupted artifact theo rule đã chốt, không sửa tay file corrupted.
- [ ] Reload `data/raw/crossref_records.json` và rerun cleaning với cùng rule/run date để tạo repaired artifact riêng.
- [ ] Đối chiếu repaired/baseline: schema, row count, tập `paper_id`, nội dung canonical và cùng test set; metric recovery một mình không đủ.

### 03:15–04:00 — Release
- [ ] Bàn giao path artifact, provenance snapshot, rule/seed corruption và kết quả đối chiếu.
- [ ] Chỉ sẵn sàng demo/release sau verification và consumer accept đúng contract.

## Handoff hai chiều

| Luồng | Producer → Consumer | Artifact/contract | Accept | Blocker behavior |
| --- | --- | --- | --- | --- |
| Baseline | Vai trò 2 → Vai trò 1 | Raw snapshot, baseline CSV/JSON, clean contract | Vai trò 1 trả lời đúng schema, row count, tập `paper_id`, run date, path | Dừng build/rebuild index; sửa nguồn/cleaning rồi phát hành snapshot mới có provenance |
| Corruption/recovery | Vai trò 1 → Vai trò 2 | Seed, mutation plan, yêu cầu rebuild `corruption_flow.py` | Vai trò 2 trả lời đúng seed, target, log fields, artifact cần tạo | Dừng mutation; không tự suy đoán rule |
| Clean data | Vai trò 2 → Vai trò 3 | Ba trạng thái clean, raw provenance, corruption log | Vai trò 3 trả lời đúng schema, row count, tập `paper_id`, snapshot/path | Dừng quality/freshness với artifact mơ hồ; trả mismatch về Vai trò 2 |
| Quality finding | Vai trò 3 → Vai trò 2 | Báo cáo schema/freshness/quality và record lỗi | Vai trò 2 trả lời đúng artifact, rule tái lập, recovery source | Dừng release; reload raw snapshot/rerun cleaning, không vá tay |
| Demo data | Vai trò 2 → Vai trò 4 | Clean contract, baseline freeze, provenance, recovery criteria | Vai trò 4 trả lời đúng schema, row count, `paper_id`, canonical check, cùng test set | Dừng demo/release phụ thuộc; Vai trò 4 không đổi data để demo pass |
| Release finding | Vai trò 4 → Vai trò 2 | Nhu cầu demo/release, sai lệch artifact, acceptance result | Vai trò 2 trả lời đúng snapshot, run date, corruption log, trạng thái re-clean | Dừng handoff; tái tạo từ raw và yêu cầu accept lại |

## Tiêu chí recovery

Repaired chỉ accept nếu schema, row count, tập `paper_id`, nội dung canonical của từng record và test set đều tương đương baseline. Metric recovery một mình không đủ vì có thể che giấu mất record hoặc đổi nội dung.

## Rủi ro

| Rủi ro | Owner | Detection | Response |
| --- | --- | --- | --- |
| Endpoint Crossref chưa rõ | Vai trò 2 + Vai trò 1 | Không xác định URL/params khi review | Chặn fetch, chốt endpoint/query/filter |
| Nguồn thay đổi | Vai trò 2 | Hash raw, row count/provenance khác | Freeze snapshot; version mới chỉ khi duyệt |
| Thiếu record | Vai trò 2 | Required fields, row count, tập `paper_id` thiếu | Rerun fetch/load hoặc reload snapshot; log lý do loại |
| Corruption không deterministic | Vai trò 1 + Vai trò 2 | Cùng seed cho artifact/log khác | Chặn đánh giá; cố định seed, input order, mutation log |
| Duplicate lookup | Vai trò 2 | `paper_id` trùng/nhiều record map DOI | Deduplicate theo rule chốt và handoff lại |
| Freshness overwrite | Vai trò 2 + Vai trò 3 | Raw/baseline bị ghi đè khi refresh | Không ghi đè snapshot freeze; version hóa provenance |

## Lệnh kiểm chứng PowerShell

```powershell
# Quét stub còn lại (starter repo dự kiến có TODO/NotImplementedError).
rg -n "TODO\(student\)|NotImplementedError" src

# Chạy hai pipeline sau khi các owner hoàn tất implementation.
.\.venv\Scripts\python.exe -m pipelines.phase1
.\.venv\Scripts\python.exe -m pipelines.corruption_flow

# Liệt kê artifact và đọc corruption log.
Get-ChildItem -LiteralPath data\raw,data\clean,data\results -File |
  Where-Object { $_.Name -match 'crossref|papers_clean|corruption_log' } |
  Select-Object FullName,Length,LastWriteTime
Get-Content -Raw -LiteralPath data\results\corruption_log.json
```

## Checklist demo/release của Vai trò 2

- [ ] Consumer đã accept chính xác snapshot và clean contract.
- [ ] Raw, baseline, corrupted, repaired artifact có đúng path/provenance.
- [ ] `corruption_log.json` có seed/rule/target tái lập được.
- [ ] Recovery đối chiếu schema, row count, tập `paper_id`, canonical content, cùng test set.
- [ ] Vai trò 1, 3, 4 đã phản hồi accept hoặc blocker; không bypass contract.
- [ ] Không secret, manual corrupted patch hay baseline copy giả repaired.
