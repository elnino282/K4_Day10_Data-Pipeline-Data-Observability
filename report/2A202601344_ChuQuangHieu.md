# Báo cáo cá nhân — Chu Quang Hiếu

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Chu Quang Hiếu |
| MSSV | 2A202601344 |
| Khóa/Lớp | K4 |
| Tên nhóm | K4 Day 10 — Data Pipeline & Observability |
| Vai trò chính | Role 2 — Nền tảng dữ liệu & recovery |
| Repository | [GitHub](https://github.com/elnino282/K4_Day10_Data-Pipeline-Data-Observability) |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

| Module/deliverable | File/hàm phụ trách | Input | Output | Trạng thái |
|---|---|---|---|---|
| Crossref ingestion | `src/ingestion/crossref.py` | Endpoint, query, filter | Raw response và `PaperRecord[]` | Hoàn thành |
| Cleaning/data model | `src/ingestion/cleaning.py` | Raw records, run date | Clean CSV/JSON 24 dòng | Hoàn thành |
| Corruption/recovery | `src/ingestion/corruption.py` | Baseline clean/raw snapshot | Corrupted data, log, repaired data | Hoàn thành |
| Provenance/freeze | `src/ingestion/provenance.py` trên nhánh role 2 | Raw/clean artifacts | Baseline manifest | Hoàn thành ở nhánh role 2; bản tích hợp dùng artifact gates tương đương |

Ngoài phạm vi chính, tôi phối hợp với role 1 để khóa raw snapshot và với role 3/4 để thống nhất `paper_id`, `text_for_embedding`, `age_days` và các đường dẫn artifact.

## 3. Kết quả theo vai trò

| Nhiệm vụ | Bằng chứng | Kết quả | Xác minh |
|---|---|---|---|
| Fetch, retry/backoff, parse Crossref | `data/raw/crossref_response.json`, `crossref_records.json` | 24 bản ghi có DOI ổn định | Chạy phase 1/đọc JSON |
| Chuẩn hóa và deduplicate | `data/clean/papers_clean.*` | 24 ID duy nhất, đủ embedding text | Quality 13/13 |
| Tạo 6 dạng corruption có log | `data/results/corruption_log.json` | Drop, blank/noise, truncate, stale, duplicate | Đối chiếu affected IDs |
| Recovery từ raw snapshot | `data/quality/repair_validation.json` | 24/24 ID phục hồi, không thiếu/thừa | `document_identity_restored=true` |

Output tiêu biểu là cặp raw snapshot có thể truy vết và ba bộ clean tách biệt; recovery được dựng lại từ raw thay vì vá file lỗi hoặc sao chép baseline.

## 4. Giải thích kỹ thuật

Phần việc giải quyết tính tái lập và độ tin cậy của dữ liệu đầu vào. Payload Crossref được bóc tách DOI, title, abstract JATS/HTML, tác giả, subject và ngày; lỗi 429/5xx/timeout được retry có giới hạn. Cleaning chuẩn hóa Unicode NFKC/whitespace, kiểm tra trường bắt buộc, deduplicate theo DOI, tính `age_days`, `summary_chars` và ghép `text_for_embedding` deterministically.

| Thành phần | Mô tả |
|---|---|
| Input | Crossref payload hoặc `crossref_records.json` |
| Output | DataFrame clean với `paper_id`, nội dung, metadata, freshness fields |
| Module phụ thuộc | `src/core/config.py`, `src/core/utils.py` |
| Consumer | Index role 3; test set/quality role 4; pipelines role 1 |
| Điều kiện lỗi | HTTP tạm thời, DOI/title/summary/date thiếu, duplicate, schema lệch |

```powershell
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

Kết quả được kiểm chứng qua 24 raw/clean records, corruption log và repair validation; bộ test chung hiện đạt 45 passed, 5 subtests passed.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** cần repair nhưng vẫn chứng minh được nguồn gốc dữ liệu.
- **Phương án cân nhắc:** sửa trực tiếp corrupted rows; copy baseline; hoặc rebuild từ raw snapshot đã khóa.
- **Lựa chọn:** rebuild bằng cùng cleaning contract từ `crossref_records.json`.
- **Lý do:** tránh che lỗi, không phụ thuộc nguồn live thay đổi và cho phép kiểm tra invariant ID/schema.
- **Bằng chứng:** repaired có 24 dòng/24 ID, không thiếu/thừa và toàn bộ metrics trở về baseline.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** payload Crossref không đồng nhất về markup, ngày và trường tùy chọn; request có thể gặp 429/5xx.
- **Nguyên nhân:** API nguồn sống và schema linh hoạt.
- **Xử lý:** parser có fallback, làm sạch markup, chọn ngày khả dụng, retry/backoff và lưu cả response lẫn normalized snapshot.
- **Xác minh:** raw artifacts parse được, baseline quality 13/13 và tests ingestion/data pipeline pass.
- **Bài học:** raw snapshot bất biến là nền tảng cho cả audit lẫn recovery.

## 7. Hiểu biết end-to-end

Crossref được lưu raw, chuyển thành clean contract, nhúng bằng MiniLM và nạp vào ba collection Chroma riêng. Test set giữ DOI ground truth để kiểm tra top-k và câu trả lời. Quality kiểm tra schema/completeness/uniqueness/validity; freshness tập trung tuổi và ngày công bố. Cùng một test set giúp delta phản ánh thay đổi dữ liệu. Repair chỉ thành công khi ID/schema/quality phục hồi và metrics trở lại mốc, không chỉ vì script exit 0.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
|---|---:|---:|---:|---|
| Retrieval hit rate | 1.000 | 0.500 | 1.000 | Drop và suy giảm nội dung làm mất hit |
| Mean token F1 | 1.000 | 0.491 | 1.000 | Blank/noise/truncate làm sai evidence |
| Judge accuracy | 1.000 | 0.458 | 1.000 | Corruption lan tới answer quality |
| Mean judge score | 5.000 | 2.875 | 5.000 | Phục hồi hoàn toàn sau rebuild |
| Quality checks | 13/13 | 11/13 | 13/13 | Duplicate và blank summary bị phát hiện |
| Freshness | fresh | stale_or_invalid | fresh | Hai stale rows làm đổi trạng thái |

Chuỗi bằng chứng: corruption có log → uniqueness/completeness/freshness suy giảm → retrieval và answer metrics giảm. Rebuild từ raw → 24 ID canonical trở lại → signal và metrics phục hồi. Drop latest kết hợp với corruption nội dung ảnh hưởng rõ nhất vì vừa làm mất ground-truth documents vừa làm yếu evidence còn lại.

## 9. Điều học được và hướng cải thiện

Tôi học được rằng data contract và snapshot quan trọng ngang thuật toán; observability cần gắn finding với ID; và RAG có thể trả lời sai dù code agent không đổi. Nếu có thêm thời gian, tôi sẽ version raw snapshot bằng manifest/hash trong bản tích hợp và đo tỷ lệ loại/dedup qua nhiều lần fetch.

## 10. Cam kết

- [x] Báo cáo phản ánh role và artifact thực tế.
- [x] Tôi hiểu luồng end-to-end và có thể truy ngược kết luận về artifact.
- [x] Không chứa credential hoặc secret.

**Họ và tên:** Chu Quang Hiếu  
**Ngày xác nhận:** 2026-08-06

