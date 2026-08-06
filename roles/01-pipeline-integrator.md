# Vai trò 1 — Điều phối pipeline

## Mục tiêu

Biến các module do ba vai trò chuyên môn bàn giao thành hai flow chạy được, tái lập được và có bằng chứng: baseline trên dữ liệu sạch, sau đó corruption → repair → comparison. Người giữ vai trò này chịu trách nhiệm về cấu hình, orchestration, release gate và demo; không làm thay implementation chuyên môn của các vai trò khác.

## Phạm vi sở hữu

| Khu vực | Ownership trực tiếp | Đầu ra chịu trách nhiệm |
| --- | --- | --- |
| `src/core/config.py` | `Paths`, `Settings`, provider/path contract | Một nguồn cấu hình thống nhất, không hard-code path/secret |
| `src/core/utils.py` | Utility dùng chung và quy ước ghi artifact | Cách đọc/ghi nhất quán giữa các module |
| `src/pipelines/phase1.py` | Baseline orchestration | Raw → clean → index → test set → evaluate → quality/freshness → report |
| `src/pipelines/corruption_flow.py` | Corruption/recovery orchestration | Corrupt → rebuild → evaluate → repair from raw → compare |
| `script/run_phase1.py` | Entrypoint baseline | Lệnh chạy end-to-end ổn định |
| `script/run_corruption_flow.py` | Entrypoint corruption/recovery | Lệnh chạy ba trạng thái ổn định |
| Release và demo | Checklist cuối, bằng chứng, trình tự trình bày | Quyết định ready/not ready có lý do |

## Không thuộc ownership

- Không viết thay ingestion, cleaning, corruption hoặc recovery logic của Vai trò 2.
- Không viết thay embedding, index, search, provider adapter hoặc agent của Vai trò 3.
- Không viết thay test set, evaluator, quality/freshness check hoặc report generator của Vai trò 4.
- Khi contract lỗi, ghi rõ producer, consumer, field/path/chữ ký sai và trả về đúng owner; không vá trực tiếp artifact JSON/CSV ở tầng orchestration.

## Contract tích hợp phải khóa

### Cấu hình và trạng thái

- Dùng `load_settings()` làm nguồn cấu hình duy nhất.
- Baseline, corrupted và repaired phải dùng cùng raw snapshot, test set, embedding model, evaluator và `top_k`.
- Ba collection phải tách biệt: `papers-baseline`, `papers-corrupted`, `papers-repaired`.
- `REFRESH_SOURCE` chỉ được bật có chủ đích trước khi khóa baseline; recovery phải load snapshot đã khóa.
- Không đọc hoặc in giá trị API key; chỉ kiểm tra credential có/không và thông báo tên biến thiếu.

### Thứ tự orchestration

```text
phase1:
settings → fetch/load raw → clean → save clean → build baseline index
→ create/load fixed test set → evaluate → quality → freshness → report → optional agent demo

corruption_flow:
load baseline artifacts → corrupt clean + log → build corrupted index
→ evaluate fixed test set → corrupted quality/freshness
→ reload raw snapshot → rerun cleaning → build repaired index
→ evaluate same test set → repaired quality/freshness → comparison report
```

### Quy tắc artifact

- Không chạy bước downstream nếu artifact upstream thiếu, rỗng hoặc sai schema.
- Không ghi đè baseline bằng output corrupted/repaired.
- Chỉ tạo Markdown report sau khi toàn bộ JSON/CSV nguồn tương ứng đã tồn tại và đọc được.
- Một script exit code `0` chưa đủ để đóng checkpoint; phải kiểm tra file, collection và nội dung tối thiểu.

## Checklist theo timeline 4 giờ

### 00:00–00:30 — Khởi động, contract và raw ingestion

- [ ] Chốt bốn ownership và dùng các file trong `roles/` làm nguồn phân công chuẩn.
- [ ] Kiểm tra Python trong khoảng 3.11–3.13 và dependency đã sẵn sàng.
- [ ] Kiểm tra `.env` cục bộ chỉ có credential của provider được chọn; không đọc giá trị ra terminal/report.
- [ ] Khóa tên/path artifact theo `Paths` trong `src/core/config.py`.
- [ ] Khóa sơ đồ handoff raw → clean → index/test set → evaluation/observability → report.
- [ ] Nhận từ Vai trò 2 đường dẫn raw response, raw records và một `paper_id` mẫu có thể truy vết.
- [ ] Gate pass: raw snapshot tồn tại, parse được và `paper_id` ổn định.
- [ ] Nếu fail: ghi blocker gồm lệnh tái hiện, owner Vai trò 2, ảnh hưởng và lựa chọn dùng snapshot/retry; chưa cho phép cleaning bắt đầu với dữ liệu bịa.

### 00:30–01:05 — Cleaning, data model và quality gates

- [ ] Khóa clean contract trước khi consumer bắt đầu build output cuối.
- [ ] Nhận raw count, clean count, số record filter/dedupe và lý do từ Vai trò 2.
- [ ] Yêu cầu Vai trò 3 xác nhận đủ field index, Vai trò 4 xác nhận đủ field test set/quality.
- [ ] Kiểm tra CSV/JSON clean cùng schema và cùng số record.
- [ ] Kiểm tra `paper_id` không null/unique, `text_for_embedding` không rỗng và `age_days` có thể tính.
- [ ] Gate pass: producer và hai consumer cùng xác nhận contract, có clean artifact đọc được.
- [ ] Nếu fail: consumer nêu chính xác field/type/path sai; trả về Vai trò 2 sửa tại nguồn, không tạo adapter tạm trong pipeline.

### 01:05–01:35 — Test set, RAG index và agent smoke test

- [ ] Khóa clean schema; thay đổi sau mốc này phải được Vai trò 2, 3 và 4 cùng chấp thuận.
- [ ] Nhận baseline collection/manifest, document count và search/lookup evidence từ Vai trò 3.
- [ ] Nhận test set path/hash, question types và kiểm tra ground-truth IDs từ Vai trò 4.
- [ ] Xác minh collection/path baseline không dùng tên corrupted hoặc repaired.
- [ ] Xác minh mọi `ground_truth_doc_ids` đều tồn tại trong baseline index.
- [ ] Ghi provider/model dùng cho agent demo mà không ghi credential.
- [ ] Gate pass: test set, manifest, collection, semantic search, exact lookup và agent smoke có evidence.
- [ ] Nếu fail: xác định lỗi thuộc data contract, index hay test set; giữ nguyên baseline input và giao đúng owner sửa.

### 01:35–02:00 — Baseline end-to-end

- [ ] Hoàn thiện `src/pipelines/phase1.py` theo thứ tự contract đã khóa.
- [ ] Chạy `uv run python script/run_phase1.py` từ project root.
- [ ] Kiểm tra raw, clean, embedding manifest, test set, answers, metrics, quality, freshness và phase-1 report.
- [ ] Yêu cầu Vai trò 3 demo một semantic search và một exact lookup.
- [ ] Yêu cầu Vai trò 4 giải thích ít nhất một retrieval hit/miss bằng ID/context thật.
- [ ] Đối chiếu số trong report với JSON/CSV nguồn.
- [ ] Gate pass: baseline artifact đầy đủ, nhất quán và có thể tái chạy từ entrypoint.
- [ ] Nếu fail: lưu traceback/command, không sửa tay output; mở lại checkpoint owner tương ứng.

### 02:00–02:15 — Nghỉ và khóa baseline

- [ ] Ghi checklist baseline, blocker còn lại và trạng thái ready/not ready.
- [ ] Khóa raw snapshot, clean baseline, test set, manifest/collection và baseline metrics làm mốc so sánh.
- [ ] Chốt các query/case demo sẽ chạy lại ở corrupted và repaired.
- [ ] Không refresh source, đổi test set, model, evaluator hoặc `top_k` sau khi khóa.
- [ ] Nghỉ đủ 15 phút; không dùng khoảng này để âm thầm thay contract.

### 02:15–03:15 — Corruption có kiểm soát và đo impact

- [ ] Hoàn thiện phần corrupt → rebuild → evaluate → quality/freshness trong `src/pipelines/corruption_flow.py`.
- [ ] Kiểm tra path/collection corrupted tách khỏi baseline trước khi ghi.
- [ ] Nhận corruption log có loại lỗi, record ID, tham số, before/after và count từ Vai trò 2.
- [ ] Nhận `papers-corrupted` và retrieval evidence cùng query baseline từ Vai trò 3.
- [ ] Nhận corrupted answers/metrics/quality/freshness từ Vai trò 4.
- [ ] Đối chiếu corruption log → quality/freshness signal → retrieval/answer metric; ghi cả signal không đổi.
- [ ] Gate pass: corrupted artifacts đầy đủ, baseline nguyên vẹn và impact có thể audit.
- [ ] Nếu fail: dừng trước repair; không thay test set hoặc chỉnh metrics để tạo chênh lệch giả.

### 03:15–04:00 — Recovery, comparison, review và demo

- [ ] Điều phối Vai trò 2 reload raw snapshot và chạy lại cleaning để tạo repaired data.
- [ ] Xác minh recovery không copy baseline và không sửa trực tiếp corrupted data.
- [ ] Nhận `papers-repaired`, manifest và cùng-query evidence từ Vai trò 3.
- [ ] Nhận repaired answers/metrics/quality/freshness và comparison report từ Vai trò 4.
- [ ] Kiểm tra repaired schema, row count, tập `paper_id` và nội dung canonical với baseline.
- [ ] Chạy lại `uv run python script/run_corruption_flow.py` từ đầu khi đủ thời gian.
- [ ] Kiểm tra report có baseline/corrupted/repaired, delta, mức phục hồi và giới hạn kết luận.
- [ ] Chạy secret scan và xác nhận `.env` không nằm trong Git.
- [ ] Gate pass: có thể demo bằng artifact thật và giải thích được trường hợp recovery chưa hoàn toàn.
- [ ] Nếu fail: công bố rõ phần chưa ready, evidence hiện có và bước tái hiện; không tuyên bố release thành công.

## Handoff và SLA phối hợp

| Producer → consumer | Gói bàn giao bắt buộc | Cách accept | Khi không đạt |
| --- | --- | --- | --- |
| Vai trò 2 → Vai trò 1 | Raw/clean/corrupted/repaired path, schema/count, corruption log, recovery evidence | File đọc được, contract đúng, state không ghi đè | Vai trò 1 ghi blocker; Vai trò 2 sửa tại nguồn |
| Vai trò 3 → Vai trò 1 | Collection, manifest, model, document count, search/lookup/agent evidence | Path và collection khớp state; query có nguồn | Trả lỗi index/provider cho Vai trò 3 |
| Vai trò 4 → Vai trò 1 | Test-set path/hash, answers, metrics, quality/freshness, reports | JSON parse được; report khớp số liệu | Trả metric/check/report mismatch cho Vai trò 4 |
| Vai trò 1 → cả nhóm | Contract đã khóa, checkpoint state, run command, blocker/release decision | Owner xác nhận dependency và deadline | Escalate khi contract thay đổi hoặc gate trễ |

Mỗi bàn giao dùng mẫu:

```text
Checkpoint:
Producer / consumer:
Artifact hoặc contract:
Lệnh/kiểm tra đã chạy:
Kết quả PASS/FAIL:
Blocker và phạm vi ảnh hưởng:
Owner xử lý / hạn xử lý:
Xác nhận không ghi đè state khác:
```

## Cách xử lý blocker

1. Tái hiện bằng một command ngắn và giữ nguyên input gây lỗi.
2. Phân loại: environment, data contract, index/agent, evaluator/observability hoặc orchestration.
3. Giao đúng owner; integrator không sửa thay module chuyên môn.
4. Trong lúc chờ, các role chuẩn bị smoke test, kiểm tra contract hoặc report skeleton trong phạm vi riêng.
5. Chỉ thay contract khi producer và consumer đồng ý; ghi lại field/path/signature thay đổi.
6. Nếu blocker đe dọa checkpoint tiếp theo, giảm phạm vi demo nhưng không bỏ evidence hoặc làm sai phép so sánh.

## Rủi ro do người điều phối sở hữu

| Rủi ro | Cách phát hiện | Hành động |
| --- | --- | --- |
| `source_api` chưa phải URL endpoint cụ thể | Review `Settings` trước fetch | Chốt endpoint với Vai trò 2, không hard-code rải rác |
| Freshness của ba state ghi đè nhau | So path trước từng lần chạy | Khóa naming riêng theo state trước orchestration |
| `generate_corruption_report()` thiếu baseline quality/freshness input | So chữ ký với yêu cầu report | Chốt contract bổ sung hoặc cách load artifact với Vai trò 4 trước implement |
| Pipeline báo done nhưng artifact thiếu/rỗng | Artifact gate sau mỗi run | Fail checkpoint dù exit code bằng 0 |
| Recovery fetch dữ liệu sống mới | So raw snapshot/path/hash | Buộc load snapshot baseline |
| Test set/model/`top_k` đổi giữa các state | Ghi config và test-set identity ở baseline | Dừng comparison và chạy lại state sai |
| Judge fallback hoặc Ragas skip bị che | Review answers/metrics payload | Yêu cầu Vai trò 4 ghi trạng thái rõ trong report |
| Secret lọt vào source/report | `git grep` trước release | Gỡ secret, rotate nếu cần, chạy scan lại |

## Tiêu chí hoàn thành

- [ ] `src/pipelines/phase1.py` và `src/pipelines/corruption_flow.py` không còn stub cần cho bài nộp.
- [ ] Hai entrypoint chạy từ project root bằng lệnh trong tài liệu.
- [ ] Baseline, corrupted và repaired có dataset, collection/manifest, answers, metrics và quality/freshness riêng.
- [ ] Baseline không bị ghi đè trong corruption flow.
- [ ] Cả ba state dùng cùng raw snapshot, test set, embedding model, evaluator và `top_k`.
- [ ] Recovery được dựng lại từ raw snapshot và có invariant ngoài metrics.
- [ ] Report khớp artifact và nêu trung thực signal/metric không đổi.
- [ ] Có một hit/miss, một corruption evidence chain và một repair evidence chain cho demo.
- [ ] Không có secret hoặc `.env` trong Git/report/log.

## Lệnh kiểm chứng

Chỉ đánh dấu checklist hoàn thành sau khi thực sự chạy và đọc kết quả:

```powershell
rg -n "TODO\(student\)|NotImplementedError" src
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
Get-ChildItem -Recurse data\raw,data\clean,data\embeddings,data\eval,data\results,data\quality,data\reports
git grep -n -I -E "AIza|sk-[A-Za-z0-9]|API_KEY=.+"
```

Kỳ vọng khi release: hai pipeline thành công, artifact đầy đủ/đọc được, không có state bị ghi đè và secret scan không phát hiện credential thật. Ở trạng thái starter hiện tại, lệnh quét stub có kết quả là bình thường và là worklist, không phải bằng chứng hoàn thành.

## Runbook demo ngắn

- [ ] Mở sơ đồ raw → clean → index → evaluate/observe → corrupt → repair → compare.
- [ ] Cho thấy ba dataset và ba collection/manifest tách biệt.
- [ ] Chạy cùng một query trên baseline, corrupted và repaired.
- [ ] Mở test set cố định và một answer artifact để giải thích retrieval hit/miss.
- [ ] Mở quality/freshness cùng comparison report; nối data change với metric change.
- [ ] Nêu một giới hạn hoặc recovery chưa hoàn toàn nếu số liệu cho thấy như vậy.
- [ ] Kết thúc bằng command tái hiện và commit/version dùng để demo.
