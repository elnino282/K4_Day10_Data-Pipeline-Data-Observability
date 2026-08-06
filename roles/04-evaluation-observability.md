# Vai trò 4 — Evaluation & observability

## Mục tiêu và ownership

Vai trò 4 chịu trách nhiệm tạo bằng chứng có thể kiểm tra để trả lời hai câu hỏi: dữ liệu lỗi ảnh hưởng đến retrieval/câu trả lời ra sao, và repair có phục hồi chất lượng hay không. Kết luận chỉ được viết từ artifact thực tế; trạng thái hiện tại của repository là starter chưa hoàn thành.

Phạm vi sở hữu:

- `src/evaluation/`: test set, answers và metrics evaluation.
- `src/observability/`: quality checks, freshness và hàm tạo báo cáo.
- `data/eval/`: evaluation set cố định dùng trong phép so sánh.
- Evaluation outputs trong `data/results/`: answers và metrics của baseline, corrupted, repaired.
- `data/quality/`: quality/freshness artifact theo từng trạng thái.
- Pipeline reports trong `data/reports/`: báo cáo baseline và comparison.

Ngoài phạm vi sở hữu:

- Không sở hữu data repair hoặc quyết định nguồn raw dùng để repair.
- Không sở hữu implementation của embedding/index hoặc agent retrieval.
- Không sở hữu orchestration trong `src/pipelines/` và các entrypoint trong `script/`.
- Có trách nhiệm phát hiện và bàn giao lỗi contract cho đúng owner, không vá trực tiếp output metrics hoặc answers.

## Contract evaluation set

Mỗi sample trong `data/eval/test_set.json` phải có đủ:

| Trường | Contract |
| --- | --- |
| `id` | ID duy nhất, ổn định trong test set. |
| `question_type` | Một trong `summary`, `authors`, `date`, `categories`. |
| `question` | Câu hỏi có thể trả lời từ corpus đã clean. |
| `ground_truth` | Đáp án tham chiếu lấy từ clean data thật. |
| `ground_truth_doc_ids` | Danh sách `paper_id` thật, tồn tại trong clean data và index. |

Nguyên tắc so sánh:

- Dùng cùng một test set, evaluator, embedding model và `top_k` cho baseline, corrupted và repaired.
- Không tạo lại ground truth từ corrupted data và không loại câu hỏi chỉ vì corruption làm câu trả lời xấu đi.
- Ghi nhận path và hash của test set khi freeze baseline; ba lần evaluation phải trỏ về cùng artifact đó.
- Kiểm tra từng `ground_truth_doc_ids` với clean/index trước evaluation; ID tự tạo hoặc ID bị thiếu là blocker.
- Giữ nguyên cách judge và cấu hình Ragas giữa ba trạng thái; nếu judge fallback hoặc Ragas lỗi thì ghi rõ trạng thái, không trình bày như evaluation đầy đủ.

## Contract quality và freshness

Mỗi trạng thái `baseline`, `corrupted`, `repaired` phải có artifact riêng, không ghi đè lẫn nhau. Payload cần đủ bằng chứng sau:

| Nhóm signal | Nội dung tối thiểu |
| --- | --- |
| Volume | Row count quan sát được và ngưỡng/kỳ vọng. |
| Identity | Số `paper_id` null, số ID duplicate và kết quả unique. |
| Completeness | Title null/rỗng; summary null/rỗng hoặc không đạt độ dài kỳ vọng. |
| Duplication | Số row/document duplicate và tiêu chí xác định. |
| Validity | Ngày parse lỗi, `age_days` thiếu/âm/không hợp lệ. |
| Freshness | Latest date, oldest date, stale count, total rows, threshold ngày và status fresh/stale/unknown. |
| Audit | Tên trạng thái, thời điểm đo, input artifact và pass/fail của từng check. |

Quality report không được hard-code pass. Freshness phải dùng ngày và `age_days` của artifact thật cùng `settings.freshness_threshold_days`. Nếu chưa có path riêng cho freshness corrupted/repaired, phải dừng tích hợp để thống nhất tên path với Vai trò 1 trước khi chạy.

## Kế hoạch theo checkpoint

### 00:00–00:30 — Đọc contract và thiết kế evaluation/observability

- [ ] Đọc `src/evaluation/testset.py`, `src/evaluation/metrics.py`, `src/observability/quality.py`, `src/observability/reporting.py`.
- [ ] Chốt schema test set, bốn `question_type` và nguồn ground truth từ clean data thật.
- [ ] Chốt danh sách quality/freshness signal, threshold và quy ước artifact riêng theo trạng thái.
- [ ] Thống nhất với Vai trò 1 cách truyền path, test-set hash, metrics và report inputs.
- [ ] Gửi cho Vai trò 2 danh sách cột clean bắt buộc: `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `published`, `age_days`, `summary_chars`, `text_for_embedding`.
- [ ] Gửi cho Vai trò 3 contract document ID, embedding model và `top_k` phải giữ cố định.

### 00:30–01:05 — Nhận quality baseline input

- [ ] Nhận sample cleaned dataframe và schema/version từ Vai trò 2.
- [ ] Xác minh row count, null/unique ID, title/summary, duplicate, dates và `age_days` trên input thật.
- [ ] Xác minh quality result chứa observed value, expectation và pass/fail thay vì chỉ có status tổng.
- [ ] Escalate nếu clean schema thiếu cột, `paper_id` không ổn định hoặc input rỗng.
- [ ] Chuẩn bị freshness payload gồm latest/oldest, stale count, threshold và status.

### 01:05–01:35 — Tạo test set và kiểm tra nhất quán với index

- [ ] Tạo sample `summary`, `authors`, `date`, `categories` từ cleaned dataframe.
- [ ] Ghi `data/eval/test_set.json` với đủ năm trường contract.
- [ ] Kiểm tra test set không rỗng, `id` unique và ground truth không rỗng.
- [ ] Đối chiếu toàn bộ `ground_truth_doc_ids` với clean data và collection baseline do Vai trò 3 bàn giao.
- [ ] Ghi path và hash test set để freeze.
- [ ] Xác nhận embedding model và `top_k` baseline trước khi evaluation.

### 01:35–02:00 — Baseline evaluation và report

- [ ] Chạy evaluator để tạo baseline answers và metrics từ test set đã khóa.
- [ ] Đọc ít nhất một retrieval hit và một retrieval miss; đối chiếu question, ground truth, retrieved IDs và contexts.
- [ ] Ghi rõ judge dùng LLM hay heuristic fallback; escalate mọi fallback không chủ đích.
- [ ] Ghi rõ Ragas enabled/skipped/error và không coi lỗi Ragas là số đo hợp lệ.
- [ ] Chạy quality/freshness trên baseline input và lưu artifact baseline riêng.
- [ ] Tạo `data/reports/phase1_report.md` từ source summary, metrics, quality và freshness thật.
- [ ] Đối chiếu mọi số trong report với JSON/CSV nguồn trước khi bàn giao.

### 02:00–02:15 — Freeze baseline

- [ ] Freeze test-set path/hash, evaluator config, embedding model và `top_k`.
- [ ] Freeze baseline answers, metrics, quality/freshness và report path; không ghi đè ở pha sau.
- [ ] Gửi Vai trò 1 manifest artifact baseline và blocker còn mở.
- [ ] Gửi Vai trò 2 danh sách quality issue cần phân biệt với corruption có chủ đích.
- [ ] Gửi Vai trò 3 một hit/miss mẫu để tái dùng khi so sánh collection.

### 02:15–03:15 — Corrupted evaluation và observability

- [ ] Nhận corrupted clean artifact và corruption log từ Vai trò 2 thông qua Vai trò 1.
- [ ] Nhận collection/manifest corrupted riêng từ Vai trò 3; xác nhận baseline không bị mutate.
- [ ] Evaluate corrupted bằng đúng test set, evaluator, embedding model và `top_k` đã freeze.
- [ ] Lưu corrupted answers/metrics vào path riêng.
- [ ] Chạy quality/freshness corrupted và lưu artifact riêng, không ghi đè baseline.
- [ ] Nối từng corruption có evidence với quality/freshness signal và metric/answer thay đổi.
- [ ] Ghi cả signal không đổi; không suy diễn impact nếu metrics không thay đổi.
- [ ] Escalate empty test set, missing ground-truth IDs, judge fallback, Ragas error hoặc freshness overwrite.

### 03:15–04:00 — Repaired comparison, demo và release

- [ ] Nhận repaired clean artifact có lineage từ raw/source đáng tin của Vai trò 2/Vai trò 1.
- [ ] Nhận collection/manifest repaired riêng từ Vai trò 3.
- [ ] Evaluate repaired bằng cấu hình đã freeze và lưu answers/metrics riêng.
- [ ] Chạy quality/freshness repaired, xác minh artifact không ghi đè hai trạng thái trước.
- [ ] Tạo comparison report với baseline, corrupted, repaired, delta và mức phục hồi.
- [ ] Hoàn thành chuỗi bằng chứng corruption impact.
- [ ] Hoàn thành chuỗi bằng chứng repair outcome, kể cả trường hợp chưa phục hồi hoàn toàn.
- [ ] Rà soát demo/release checklist của vai trò trước khi công bố kết quả.

## Handoff và blocker behavior

| Producer | Consumer | Artifact/contract | Cách accept | Blocker behavior |
| --- | --- | --- | --- | --- |
| Vai trò 2 | Vai trò 4 | Cleaned dataframe/CSV/JSON với schema bắt buộc và stable `paper_id`. | Đọc được; không rỗng; cột đủ; ID không null/unique; dates và `age_days` kiểm tra được. | Dừng build test set; gửi danh sách cột/ID lỗi và sample evidence cho Vai trò 2, đồng thời báo Vai trò 1. |
| Vai trò 3 | Vai trò 4 | Baseline/corrupted/repaired index manifest, collection riêng, embedding model và `top_k`. | Mọi ground-truth ID baseline tồn tại; collection/path tách biệt; model và `top_k` khớp manifest freeze. | Dừng evaluation trạng thái lỗi; không đổi test set để né missing ID; gửi IDs/config mismatch cho Vai trò 3 và Vai trò 1. |
| Vai trò 4 | Vai trò 1 | Test-set path/hash, evaluation config, answers/metrics, quality/freshness và report inputs theo trạng thái. | File đọc được; schema đủ; test hash/config nhất quán; report value truy ngược được về artifact. | Không cho pipeline/report đánh dấu hoàn thành; gửi blocker kèm path và observed mismatch, không sửa metrics thủ công. |
| Vai trò 4 | Vai trò 2 | Quality/freshness findings và document-level evidence liên quan corruption/repair. | Mỗi finding có state, check, observed value, affected IDs/count và artifact path. | Nếu không truy được tới row/ID thật, hạ kết luận thành chưa xác minh và yêu cầu artifact mới. |
| Vai trò 4 | Vai trò 3 | Hit/miss evidence: question, expected IDs, retrieved IDs, contexts và config. | Có thể tái hiện trên đúng collection, model và `top_k`; không lẫn ba trạng thái. | Nếu collection hoặc config khác baseline freeze, loại kết quả khỏi comparison và yêu cầu chạy lại. |

## Escalation bắt buộc

- Empty test set: dừng evaluation; không tạo metrics rỗng hoặc report giả.
- Missing `ground_truth_doc_ids`: dừng evaluation; gửi danh sách ID thiếu cho Vai trò 2 và 3.
- Judge fallback: ghi số sample/reasoning bị fallback; báo Vai trò 1 trước khi dùng judge metrics để kết luận.
- Ragas error: lưu lỗi đã che secret, đánh dấu Ragas không hợp lệ; các metric còn lại phải được đánh giá riêng.
- Freshness overwrite: dừng flow, bảo toàn artifact còn lại và thống nhất path riêng với Vai trò 1; không chạy tiếp bằng file đã bị ghi đè.

## Tiêu chí hoàn thành

- [ ] Không còn stub thuộc phạm vi `src/evaluation/` và `src/observability/`.
- [ ] Test set đủ contract, có path/hash freeze và dùng chung cho ba trạng thái.
- [ ] Evaluator, embedding model và `top_k` giống nhau trong ba lần đánh giá.
- [ ] Answers, metrics, quality và freshness tồn tại riêng cho baseline/corrupted/repaired.
- [ ] Một retrieval hit và một retrieval miss đã được kiểm tra đến IDs/contexts nguồn.
- [ ] Corruption impact có chuỗi: corruption artifact → quality/freshness signal → retrieval/answer metric.
- [ ] Repair outcome có chuỗi: repair artifact → quality/freshness recovery → metric recovery hoặc bằng chứng chưa recovery.
- [ ] Phase 1 và comparison report khớp artifact thực tế, không chứa secret và không tuyên bố quá mức.

## Lệnh kiểm chứng PowerShell

Các lệnh dưới đây chỉ được coi là pass sau khi implementation hoàn tất và output đã được đọc; repository starter hiện chưa đáp ứng điều đó.

```powershell
rg -n "TODO\(student\)|NotImplementedError" src/evaluation src/observability

uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py

Get-Content -Raw data/eval/test_set.json
Get-Content -Raw data/results/baseline_metrics.json
Get-Content -Raw data/results/corrupted_metrics.json
Get-Content -Raw data/results/repaired_metrics.json
Get-ChildItem -Recurse data/quality | Select-Object FullName, Length
Get-Content -Raw data/reports/phase1_report.md
Get-Content -Raw data/reports/corruption_report.md
```

Kiểm tra consistency bổ sung:

```powershell
$testSet = Get-Content -Raw data/eval/test_set.json | ConvertFrom-Json
$testSet.Count
$testSet | Group-Object id | Where-Object Count -gt 1
$testSet | Select-Object -ExpandProperty question_type | Sort-Object -Unique
Get-FileHash data/eval/test_set.json -Algorithm SHA256
```

## Checklist demo/release riêng của Vai trò 4

- [ ] Demo test-set path/hash và giải thích vì sao phải freeze.
- [ ] Demo một hit và một miss bằng answers artifact, retrieved IDs và contexts.
- [ ] Demo quality/freshness artifact riêng của cả ba trạng thái.
- [ ] Demo bảng comparison và chỉ ra số liệu nguồn của từng dòng.
- [ ] Trình bày một corruption impact evidence chain và một repair outcome evidence chain.
- [ ] Nêu rõ judge fallback, Ragas error/skipped hoặc signal không đổi nếu có.
- [ ] Xác minh report không chứa `.env`, API key, token hoặc secret.
- [ ] Xác minh không nhận ownership cho repair, index implementation hoặc orchestration.
- [ ] Chỉ bàn giao release khi Vai trò 1 accept test hash/config và toàn bộ artifact contract.
