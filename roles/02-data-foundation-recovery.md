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

### 00:00–00:30 — Chốt nguồn
- [ ] Xác minh endpoint/query/filter Crossref với Vai trò 1.
- [ ] Chốt mapping payload sang `PaperRecord`, quy tắc `paper_id`, run date, sort và deduplicate.
- [ ] Fetch/load Crossref trong `src/ingestion/crossref.py`; lưu raw HTTP response và `PaperRecord` snapshot vào `data/raw/crossref_response.json` và `data/raw/crossref_records.json`, kèm provenance nguồn/query/filter.
- [ ] Dùng retry/backoff có giới hạn cho lỗi tạm thời (đặc biệt 429/503), log lỗi cuối không kèm credential.
- [ ] Gate raw pass: hai artifact raw tồn tại, parse được, có `paper_id` ổn định và provenance đủ để tái lập; nếu fail, dừng cleaning và trả endpoint/path/row expected-vs-actual cùng command tái hiện cho Vai trò 1.

### 00:30–01:05 — Cleaning truy vết
- [ ] Nhận `data/raw/crossref_records.json` đã pass raw gate làm input cleaning; không fetch/load nguồn sống ở checkpoint này.
- [ ] Chuẩn hóa và ghi/return record vào, record loại, lý do loại, rule normalize, duplicate key.
- [ ] Tạo clean contract deterministically; xuất CSV/JSON cùng schema và cùng tập `paper_id`.
- [ ] Gate clean/data model/quality: kiểm tra `paper_id` không null/unique, `text_for_embedding` không rỗng, `age_days` tính được, và CSV/JSON cùng schema/row count trước handoff.

### 01:05–01:35 — Handoff test set và index
- [ ] Gửi schema, row count, tập/hash `paper_id`, run date và path baseline clean cho Vai trò 3 (RAG/index) và Vai trò 4 (test set, quality/freshness).
- [ ] Nhận lại từ Vai trò 3 xác nhận field index; nhận từ Vai trò 4 xác nhận field test set/quality và giữ cùng baseline snapshot.

### 01:35–02:00 — Tích hợp baseline
- [ ] Phối hợp Vai trò 1 tích hợp baseline flow: raw → clean → index → test set → evaluation → quality/freshness → report.
- [ ] Xác minh baseline clean đã được Vai trò 3 và Vai trò 4 accept trước release/integration; chỉ refresh khi được chốt rõ ràng.

### 02:00–02:15 — Nghỉ và freeze baseline
- [ ] Freeze raw snapshot, baseline clean, test set và thông tin provenance; không refresh source hay đổi clean contract.
- [ ] Ghi blocker còn lại rồi nghỉ theo mốc; mọi thay đổi sau freeze phải được Vai trò 1 điều phối và consumer accept lại.

### 02:15–03:15 — Corruption có kiểm soát
- [ ] Chốt seed, loại corruption, tỷ lệ/target và format `corruption_log.json` với Vai trò 1.
- [ ] Tạo corrupted artifact theo rule deterministic/logged đã chốt, không sửa tay file corrupted và giữ baseline nguyên vẹn.

### 03:15–04:00 — Recovery, release và demo
- [ ] Reload `data/raw/crossref_records.json` và rerun cleaning với cùng rule/run date để tạo repaired artifact riêng.
- [ ] Đối chiếu repaired/baseline: schema, row count, tập `paper_id`, nội dung canonical và cùng test set; metric recovery một mình không đủ.
- [ ] Bàn giao path artifact, provenance snapshot, rule/seed corruption và kết quả đối chiếu cho Vai trò 1; chỉ sẵn sàng demo/release sau verification và consumer accept đúng contract.

## Handoff hai chiều

Mọi reject handoff phải ghi field/path/row expected so với actual và command tái hiện trước khi dừng hoặc trả về owner.

| Luồng | Producer → Consumer | Artifact/contract | Accept | Blocker behavior |
| --- | --- | --- | --- | --- |
| Baseline | Vai trò 2 → Vai trò 1 | Raw snapshot, baseline CSV/JSON, clean contract | Vai trò 1 trả lời đúng schema, row count, tập `paper_id`, run date, path | Dừng integration/rebuild; ghi field/path/row expected-vs-actual và command tái hiện, rồi trả Vai trò 2 sửa nguồn/cleaning |
| Corruption/recovery | Vai trò 1 → Vai trò 2 | Seed, mutation plan, yêu cầu rebuild `corruption_flow.py` | Vai trò 2 trả lời đúng seed, target, log fields, artifact cần tạo | Dừng mutation; ghi field/path/row expected-vs-actual và command tái hiện, không tự suy đoán rule |
| Clean data cho RAG/index | Vai trò 2 → Vai trò 3 | Ba trạng thái clean, raw provenance, corruption log | Vai trò 3 trả lời đúng schema, row count, tập `paper_id`, snapshot/path và field index | Dừng build index; ghi field/path/row expected-vs-actual và command tái hiện, rồi trả mismatch về Vai trò 2 |
| Quality/freshness finding | Vai trò 4 → Vai trò 2 | Báo cáo schema/freshness/quality và record lỗi | Vai trò 2 trả lời đúng artifact, rule tái lập, recovery source | Dừng release artifact đó; ghi field/path/row expected-vs-actual và command tái hiện, rồi reload raw/rerun cleaning, không vá tay |
| Clean data cho evaluation/observability | Vai trò 2 → Vai trò 4 | Clean contract, baseline freeze, provenance, recovery criteria | Vai trò 4 trả lời đúng schema, row count, `paper_id`, canonical check, cùng test set | Dừng evaluation/quality/freshness phụ thuộc; ghi field/path/row expected-vs-actual và command tái hiện; Vai trò 4 không đổi data để pass |
| Release finding | Vai trò 4 → Vai trò 2 | Sai lệch quality/freshness hoặc acceptance result cần sửa dữ liệu | Vai trò 2 trả lời đúng snapshot, run date, corruption log, trạng thái re-clean | Dừng handoff; ghi field/path/row expected-vs-actual và command tái hiện, tái tạo từ raw rồi yêu cầu accept lại |

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
| Freshness overwrite | Vai trò 2 + Vai trò 4 | Raw/baseline bị ghi đè khi refresh | Không ghi đè snapshot freeze; version hóa provenance |

## Lệnh kiểm chứng PowerShell

```powershell
# Quét stub còn lại (starter repo dự kiến có TODO/NotImplementedError).
rg -n "TODO\(student\)|NotImplementedError" src

# Chạy hai pipeline sau khi các owner hoàn tất implementation.
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py

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
