# Thiết kế điều phối nhóm 4 vai trò

## Mục tiêu

Tạo bốn tài liệu vai trò độc lập giúp nhóm hoàn thành bài lab Data Pipeline & Data Observability trong bốn giờ. Mỗi tài liệu phải xác định rõ ownership, checklist theo checkpoint, handoff, artifact và tiêu chí hoàn thành dựa trên codebase hiện tại.

## Nguồn chuẩn

- Dùng mô hình nhóm bốn người trong `phan-cong-day-10-data-pipeline-4h(2).html` làm nguồn phân công chính.
- Dùng `README.md`, `Guide.md`, `Rubric.md` và code trong `src/` để xác định contract và tiêu chí kiểm chứng.
- Phân công cũ trong `report/README.md` không được dùng làm nguồn ownership vì không nhất quán với mô hình bốn vai trò đã được chọn.
- Repo hiện là starter: nhiều hàm còn `TODO(student)` hoặc `NotImplementedError`, còn `data/` chưa có artifact thực. Tài liệu vai trò phải mô tả công việc cần làm, không được diễn đạt như thể pipeline đã hoàn thành.

## Phương án tổ chức

Áp dụng mô hình hybrid ownership và checkpoint:

- Mỗi thành viên sở hữu cố định một miền kỹ thuật trong toàn bộ phiên làm việc.
- Các checkpoint không đổi ownership; chúng chỉ khóa contract, kiểm tra đầu ra và kích hoạt handoff.
- Thành viên có thể hỗ trợ miền khác nhưng không tự nhận ownership hoặc sửa contract chung mà chưa thống nhất với người điều phối.
- Mọi handoff phải chỉ ra artifact, trạng thái kiểm tra và blocker; thông báo miệng không được xem là bàn giao hoàn tất.

## Cấu trúc đầu ra

Tạo thư mục `roles/` với bốn file:

1. `roles/01-pipeline-integrator.md`
2. `roles/02-data-foundation-recovery.md`
3. `roles/03-rag-agent.md`
4. `roles/04-evaluation-observability.md`

Mỗi file dùng chung cấu trúc:

1. Mục tiêu vai trò.
2. Phạm vi sở hữu và phần không thuộc ownership.
3. File, hàm và artifact phụ trách.
4. Contract input/output.
5. Checklist theo bảy checkpoint.
6. Handoff nhận vào và bàn giao ra.
7. Blocker, escalation và quy tắc không ghi đè artifact.
8. Tiêu chí hoàn thành có thể quan sát.
9. Lệnh kiểm chứng PowerShell phù hợp repo.
10. Checklist demo/release và rủi ro đặc thù.

Checklist chỉ dùng trạng thái chưa hoàn thành (`- [ ]`) vì repo chưa có bằng chứng chạy thật.

## Ranh giới ownership

### Vai trò 1 — Điều phối pipeline

Sở hữu:

- `src/core/`
- `src/pipelines/`
- `script/`
- Cấu hình, orchestration, tích hợp, release gate và demo end-to-end.

Trách nhiệm chính:

- Khóa tên/path artifact và contract giữa các module.
- Ghép baseline flow và corruption/recovery flow theo đúng thứ tự.
- Không để corrupted hoặc repaired run ghi đè baseline.
- Chạy entrypoint, kiểm tra artifact thay vì chỉ dựa vào exit code.
- Điều phối xử lý blocker và đóng băng phạm vi trước demo.
- Kiểm tra secret, tính tái lập và sự nhất quán giữa report với artifact.

Không sở hữu implementation chi tiết của ingestion, retrieval, evaluation hoặc observability.

### Vai trò 2 — Nền tảng dữ liệu & recovery

Sở hữu:

- `src/ingestion/`
- `data/raw/`
- `data/clean/`
- `data/results/corruption_log.json`
- Phần corruption và rebuild-from-raw trong `src/pipelines/corruption_flow.py`, phối hợp với Vai trò 1.

Trách nhiệm chính:

- Fetch/load Crossref và giữ raw snapshot có lineage.
- Tạo `PaperRecord`, stable `paper_id` và clean schema.
- Sinh `text_for_embedding`, `age_days`, các trường authors/categories đã chuẩn hóa.
- Tạo corruption có chủ đích, có log và tái hiện được.
- Recovery bằng cách load raw snapshot rồi chạy lại cleaning; không sửa tay corrupted data hoặc copy baseline để giả lập repaired data.
- Bàn giao DataFrame/artifact cùng schema cho RAG, evaluation và observability.

### Vai trò 3 — RAG & agent

Sở hữu:

- `src/retrieval/`
- `data/chroma/`
- `data/embeddings/`
- `data/results/agent_demo_answers.json`

Trách nhiệm chính:

- Dùng MiniLM để embedding và ChromaDB để lưu/truy xuất.
- Tạo ba collection riêng: `papers-baseline`, `papers-corrupted`, `papers-repaired`.
- Bảo đảm manifest khớp collection, model và document count.
- Kiểm tra semantic search và exact lookup.
- Cấu hình multi-provider LLM mà không để lộ credential.
- Kiểm tra agent dùng tool trước câu hỏi factual và từ chối khi corpus không hỗ trợ.
- Bàn giao retrieved IDs, contexts và bằng chứng hit/miss cho Vai trò 4.

### Vai trò 4 — Evaluation & observability

Sở hữu:

- `src/evaluation/`
- `src/observability/`
- `data/eval/`
- Evaluation/answers artifacts trong `data/results/`
- Quality/freshness artifacts trong `data/quality/`
- Báo cáo sinh bởi pipeline trong `data/reports/`

Trách nhiệm chính:

- Tạo test set từ clean data thật với `ground_truth_doc_ids` hợp lệ.
- Khóa và tái sử dụng cùng test set cho baseline, corrupted và repaired.
- Tính và kiểm tra `retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score`; ghi rõ trạng thái Ragas hoặc judge fallback.
- Chạy quality checks và freshness bằng ngưỡng thật, không hard-code pass.
- Tạo report từ JSON/CSV thực tế, kèm delta và mức phục hồi.
- Chỉ kết luận quan hệ nhân quả khi có chuỗi bằng chứng từ corruption tới quality/freshness rồi tới retrieval/answer metric.

## Timeline và checkpoint chung

| Thời gian | Checkpoint | Release gate |
| --- | --- | --- |
| 00:00–00:30 | Khởi động, contract và raw ingestion | Chốt ownership/path/schema; raw snapshot và stable `paper_id` tồn tại |
| 00:30–01:05 | Cleaning, data model và quality gates | Clean CSV/JSON đọc được; ID unique; `text_for_embedding` và `age_days` hợp lệ |
| 01:05–01:35 | Test set, RAG index và agent smoke test | Test set, baseline manifest/collection, search, lookup và agent có bằng chứng |
| 01:35–02:00 | Baseline end-to-end | Baseline metrics, answers, quality, freshness và report khớp nhau |
| 02:00–02:15 | Nghỉ và khóa baseline | Test set, raw snapshot và baseline artifacts không bị thay đổi ngoài kiểm soát |
| 02:15–03:15 | Corruption và đo impact | Corrupted data/index/metrics/quality có path riêng và corruption log đầy đủ |
| 03:15–04:00 | Repair, comparison, review và demo | Repaired artifacts được dựng từ raw; comparison report có delta; release gate đạt |

## Contract và handoff bắt buộc

### Data foundation → RAG

Clean DataFrame phải có tối thiểu:

- `paper_id`
- `title`
- `summary`
- `published`
- `authors_joined`
- `categories_joined`
- `abs_url`
- `pdf_url`
- `text_for_embedding`

`paper_id` phải ổn định; `text_for_embedding` không rỗng; baseline không có duplicate ID.

### Data foundation → Evaluation & observability

Ngoài các trường trên, cần `age_days`, `summary_chars` và semantics rõ ràng cho null, duplicate, date. `ground_truth_doc_ids` phải lấy từ `paper_id` thật.

### RAG → Evaluation & observability

Bàn giao tên collection, embedding model, document count, retrieved document IDs/contexts và manifest path. Ba trạng thái phải dùng cùng model và `top_k`.

### Các vai trò chuyên môn → Pipeline integrator

Mỗi handoff phải có:

- đường dẫn artifact;
- command hoặc kiểm tra đã chạy;
- kết quả pass/fail;
- blocker còn lại và phạm vi ảnh hưởng;
- xác nhận không ghi đè artifact trạng thái khác.

### Pipeline integrator → Cả nhóm

Thông báo checkpoint chỉ được đóng khi release gate tương ứng đạt. Nếu chưa đạt, Vai trò 1 ghi blocker có evidence, chỉ định owner xử lý và giữ nguyên contract đã khóa trừ khi cả hai phía liên quan đồng ý thay đổi.

## Quy tắc hiệu quả và chống chồng chéo

- Không fetch lại source giữa baseline, corruption và repair nếu raw snapshot đã tồn tại; tránh làm corpus thay đổi.
- Không đổi test set, embedding model, evaluator hoặc `top_k` giữa ba trạng thái.
- Không sửa trực tiếp JSON metrics/report để làm kết quả đẹp hơn.
- Không để Vai trò 1 trở thành người làm thay tất cả module; Vai trò 1 tập trung integration, evidence và quyết định release.
- Khi contract không khớp, consumer báo chính xác cột/path/chữ ký thiếu; owner sửa tại nguồn.
- Khi một role chờ handoff, role đó chuẩn bị smoke test, kiểm tra contract hoặc report skeleton trong phạm vi của mình.
- Mỗi checkpoint ưu tiên artifact có thể kiểm chứng hơn phần trình bày.

## Tiêu chí hoàn thành toàn nhóm

- Không còn `TODO(student)` hoặc `NotImplementedError` trong các flow cần nộp.
- `uv run python script/run_phase1.py` chạy end-to-end và sinh đủ baseline artifacts.
- `uv run python script/run_corruption_flow.py` sinh đủ corrupted, repaired và comparison artifacts.
- Baseline, corrupted và repaired có dataset, manifest/collection, answers, metrics và quality/freshness tách biệt.
- Repair được dựng lại từ raw snapshot và được kiểm chứng bằng schema, row count, tập `paper_id` và metrics; không chỉ bằng lời mô tả.
- Report khớp dữ liệu nguồn và nêu trung thực metric không đổi hoặc recovery chưa hoàn toàn.
- Có ít nhất một retrieval hit/miss và hai chuỗi nguyên nhân–bằng chứng để demo.
- Repository và report không chứa `.env`, API key, token hoặc secret.

## Rủi ro phải phản ánh trong từng file vai trò

- `Settings.source_api` đang là nhãn mô tả, chưa phải endpoint Crossref cụ thể.
- Chưa có corruption seed/invariant, nên cần quy tắc deterministic hoặc log đủ chi tiết.
- `Paths` chỉ có một `freshness_report`, có nguy cơ ghi đè giữa ba trạng thái.
- `generate_corruption_report()` chưa nhận baseline quality/freshness trực tiếp.
- `evaluate_pipeline()` lỗi khi test set rỗng.
- Judge có thể fallback âm thầm và Ragas mặc định bị skip.
- Metrics hiện dùng `retrieval.qa.answer_question()`, không trực tiếp đánh giá LangChain agent.
- Chroma lookup có thể ghi đè duplicate ID/title trong dictionary nội bộ.
- Model embedding có thể cần tải lần đầu; agent smoke test phụ thuộc provider hoặc Ollama.

Các rủi ro trên phải được gán owner, hành động giảm thiểu và cách phát hiện, không để ở dạng ghi chú chung không có người chịu trách nhiệm.

## Kiểm chứng tài liệu vai trò

Sau khi tạo bốn file:

1. Kiểm tra đủ bốn file và đúng tên.
2. Tìm mọi checkpoint trong từng file để bảo đảm không thiếu giai đoạn.
3. Tìm các cụm `TBD`, `TODO`, placeholder hoặc tuyên bố hoàn thành không có evidence.
4. Đối chiếu mọi path, hàm, artifact và lệnh với codebase.
5. Kiểm tra mỗi artifact chính chỉ có một owner và các role khác chỉ nhận handoff/phối hợp.
6. Kiểm tra các contract quan trọng xuất hiện ở cả phía bàn giao và phía tiếp nhận với nội dung nhất quán.
