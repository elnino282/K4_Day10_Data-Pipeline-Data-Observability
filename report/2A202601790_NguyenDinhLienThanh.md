# Báo cáo cá nhân — Nguyễn Đình Liên Thành

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Nguyễn Đình Liên Thành |
| MSSV | 2A202601790 |
| Khóa/Lớp | K4 |
| Tên nhóm | K4 Day 10 — Data Pipeline & Observability |
| Vai trò chính | Role 1 — Điều phối pipeline |
| Repository | [GitHub](https://github.com/elnino282/K4_Day10_Data-Pipeline-Data-Observability) |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

| Module/deliverable | File/hàm | Input | Output | Trạng thái |
|---|---|---|---|---|
| Cấu hình/utility | `src/core/config.py`, `utils.py` | `.env`, project path | Settings/Paths và artifact validation | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py` | Settings và module contracts | Baseline artifacts/report | Hoàn thành |
| Corruption/recovery flow | `src/pipelines/corruption_flow.py` | Frozen baseline | Ba state và comparison | Hoàn thành |
| Entrypoint/release gate | `script/run_*.py`, tests | Pipeline functions | Lệnh tái hiện, gate PASS/FAIL | Hoàn thành |

Tôi điều phối contract giữa ba role chuyên môn, kiểm tra state isolation, artifact đầy đủ và report khớp JSON; không sửa tay output để vượt gate.

## 3. Kết quả theo vai trò

| Nhiệm vụ | Bằng chứng | Kết quả | Xác minh |
|---|---|---|---|
| Ghép baseline end-to-end | `phase1.py`, `phase1_report.md` | Raw → report chạy đủ thứ tự | Chạy `run_phase1.py` |
| Ghép corrupt → repair → compare | `corruption_flow.py` | Artifact ba state không ghi đè | Chạy `run_corruption_flow.py` |
| Khóa invariant | Hash/test-set/index validators | Cùng snapshot, model, top-k, test set | `comparison_metrics.json` |
| Release verification | `tests/` | 45 passed, 5 subtests passed | `pytest -q` |

Output tiêu biểu là `comparison_metrics.json` và corruption report được sinh chỉ sau khi mọi JSON/CSV đầu vào đã tồn tại, parse được và qua gate.

## 4. Giải thích kỹ thuật

Pipeline baseline lần lượt load settings, fetch/load raw, clean, build index, tạo/load test set, evaluate, kiểm tra quality/freshness và sinh report. Flow thứ hai bảo vệ hash baseline, tạo corrupted state, evaluate, rebuild repaired từ raw snapshot, rồi so sánh. Helper validators kiểm tra file không rỗng, schema, manifest, collection name, test-set identity và canonical records.

| Thành phần | Mô tả |
|---|---|
| Input | Settings, module functions và artifact contracts của role 2–4 |
| Output | Hai flow tái lập, ba state riêng, release evidence |
| Producer phụ thuộc | Ingestion, retrieval, evaluation/observability |
| Consumer | CLI, UI, báo cáo nhóm và demo |
| Điều kiện lỗi | Artifact thiếu/rỗng, hash đổi, schema mismatch, state overwrite, credential thiếu |

```powershell
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
.\.venv\Scripts\python.exe -m pytest -q
```

Kết quả thực tế của bước xác minh cuối: 45 passed, 5 subtests passed trong 20.37 giây.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** exit code 0 chưa chứng minh pipeline tạo đúng artifact hoặc giữ phép so sánh công bằng.
- **Phương án:** chỉ dựa vào exception; hoặc thêm artifact/contract gates sau từng checkpoint.
- **Lựa chọn:** fail-fast validators và hash invariants.
- **Lý do:** lỗi được gán đúng producer, ngăn report từ dữ liệu thiếu và ngăn baseline bị ghi đè.
- **Bằng chứng:** ba state có output riêng, test-set SHA-256 giống nhau và repair validation khôi phục 24 ID.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** các module riêng lẻ chạy được nhưng có nguy cơ dùng sai path/state hoặc sinh report trước khi đủ input.
- **Nguyên nhân:** orchestration ban đầu thiếu contract gates và kiểm tra tính bất biến.
- **Xử lý:** bổ sung validation DataFrame/artifact/index manifest, chụp hash baseline và assert không đổi qua flow.
- **Xác minh:** tests core/phase1/corruption flow pass; comparison truy ngược được về artifact.
- **Bài học:** integrator phải xác minh contract, không chỉ gọi tuần tự các hàm.

## 7. Hiểu biết end-to-end

Crossref → raw snapshot → clean contract → MiniLM/Chroma → fixed evaluation → quality/freshness → corruption → evaluation lại → rebuild từ raw → comparison. DOI ground truth đo retrieval, reference answer đo F1/judge. Quality và freshness là hai lớp signal bổ sung. Cùng test set/config cô lập biến dữ liệu. Repair thành công cần cả invariant tài liệu và metric phục hồi.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
|---|---:|---:|---:|---|
| Retrieval hit rate | 1.000 | 0.500 | 1.000 | Delta -0.500/+0.500 |
| Mean token F1 | 1.000 | 0.491 | 1.000 | Delta -0.509/+0.509 |
| Judge accuracy | 1.000 | 0.458 | 1.000 | Delta -0.542/+0.542 |
| Mean judge score | 5.000 | 2.875 | 5.000 | Delta -2.125/+2.125 |
| Quality checks | 13/13 | 11/13 | 13/13 | Gate phát hiện lỗi trước release |
| Freshness | fresh | stale_or_invalid | fresh | State path riêng hoạt động đúng |

Corruption log → hai quality check fail và freshness degrade → cả bốn agent metrics giảm. Recovery từ raw → invariant 24 ID/24 rows và signal pass → metrics trở lại baseline. Kết quả đáng chú ý là quality chỉ giảm 2/13 nhưng agent metric giảm gần một nửa, cho thấy một số lỗi cục bộ có tác động downstream lớn.

## 9. Điều học được và hướng cải thiện

Tôi học được rằng orchestration cần quản lý invariant; release evidence phải machine-readable; và mức giảm quality check không tỷ lệ tuyến tính với agent impact. Nếu có thêm thời gian, tôi sẽ đóng gói preflight CLI xuất một release manifest gồm commit, config không nhạy cảm, hash và runtime của từng state.

## 10. Cam kết

- [x] Báo cáo phản ánh role và artifact thực tế.
- [x] Tôi có thể tái hiện và giải thích toàn bộ flow.
- [x] Không chứa credential hoặc secret.

**Họ và tên:** Nguyễn Đình Liên Thành  
**Ngày xác nhận:** 2026-08-06

