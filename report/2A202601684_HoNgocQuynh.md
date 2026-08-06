# Báo cáo cá nhân — Hồ Ngọc Quỳnh

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Hồ Ngọc Quỳnh |
| MSSV | 2A202601684 |
| Khóa/Lớp | K4 |
| Tên nhóm | K4 Day 10 — Data Pipeline & Observability |
| Vai trò chính | Role 3 — RAG & agent |
| Repository | [GitHub](https://github.com/elnino282/K4_Day10_Data-Pipeline-Data-Observability) |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

| Module/deliverable | File/hàm | Input | Output | Trạng thái |
|---|---|---|---|---|
| Embedding adapter | `src/retrieval/embeddings.py` | `text_for_embedding` | OpenAI hoặc SentenceTransformer vectors theo cấu hình | Hoàn thành |
| Vector index | `src/retrieval/index.py` | Clean DataFrame, state path | Ba Chroma collections/manifests | Hoàn thành |
| Deterministic QA | `src/retrieval/qa.py` | Question, search results | Answer, contexts, retrieved IDs | Hoàn thành |
| Agent/provider | `src/retrieval/agent.py`, `llm.py` | Settings và index | Tool-using RAG answer | Hoàn thành |

Tôi hỗ trợ tích hợp UI/agent demo và regression test cho câu trả lời metadata được grounded vào document đã retrieve.

## 3. Kết quả theo vai trò

| Nhiệm vụ | Bằng chứng | Kết quả | Xác minh |
|---|---|---|---|
| Build/load index theo state | `data/embeddings/*.json` | Baseline/corrupted/repaired tách biệt | Kiểm tra manifest/collection |
| Semantic search và exact lookup | `LocalEmbeddingIndex.search/lookup` | Trả ID, metadata, context có nguồn | Test retrieval/data pipeline |
| QA có truy vết | `data/results/*_answers.json` | 24 answer traces mỗi state | Đối chiếu retrieved IDs |
| Agent đa provider | `build_llm`, `build_agent` | Gemini demo thành công, không lộ key | `agent_demo_answers.json` |

Output tiêu biểu là answer artifact chứa câu hỏi, ground truth, retrieved IDs, contexts và prediction, cho phép role 4 tính metric và audit lỗi.

## 4. Giải thích kỹ thuật

Clean documents được nhúng bằng cùng model rồi lưu vào Chroma cosine. Lần chạy bàn giao dùng `text-embedding-3-small`; adapter vẫn hỗ trợ SentenceTransformer khi cấu hình model cục bộ. Collection name được suy ra theo state để không ghi đè. `search()` phục vụ semantic retrieval; `lookup()` phục vụ DOI/title chính xác. QA lấy câu trả lời factual từ metadata của kết quả đứng đầu, còn agent dùng hai tool trên và bị ràng buộc chỉ trả lời theo nguồn retrieve.

| Thành phần | Mô tả |
|---|---|
| Input | Clean schema và `text_for_embedding`; embedding model; `top_k=4` |
| Output | Index, embedding manifest, `AnswerResult` và agent response |
| Producer phụ thuộc | Role 2 cung cấp clean contract |
| Consumer | Role 4 evaluator; role 1 orchestration; UI |
| Điều kiện lỗi | Model mismatch, collection nhầm state, ground-truth ID không có, metadata thiếu |

```powershell
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
.\.venv\Scripts\python.exe -m pytest -q
```

Kết quả thực tế: 45 passed, 5 subtests passed; baseline/repaired retrieval hit rate 1.0, corrupted 0.5.

## 5. Quyết định kỹ thuật quan trọng

- **Bối cảnh:** cần so sánh ba trạng thái mà không để index cũ hoặc state khác làm nhiễu.
- **Phương án:** dùng một collection và rebuild; hoặc tách ba collection cố định.
- **Lựa chọn:** `papers-baseline`, `papers-corrupted`, `papers-repaired`.
- **Lý do:** tăng khả năng audit, tránh overwrite và cho phép chạy lại cùng query.
- **Bằng chứng:** manifest và answers của ba state độc lập; repair trở về hit rate 1.0 trên cùng hash test set.

## 6. Lỗi/blocker đã xử lý

- **Triệu chứng:** retrieval baseline hit 1.0 nhưng token F1 của câu hỏi category từng chỉ đạt 0.75.
- **Nguyên nhân:** clean data có `primary_category=uncategorized` khi Crossref thiếu subject, nhưng metadata/index chỉ ưu tiên `categories_joined`, khiến answer rỗng.
- **Xử lý:** đưa `primary_category` vào metadata contract và thêm fallback khi extract category; đồng thời siết agent chỉ dùng metadata nguồn.
- **Xác minh:** regression test pass và baseline token F1 đạt 1.0.
- **Bài học:** retrieval đúng document chưa đủ; metadata contract và answer extraction phải nhất quán.

## 7. Hiểu biết end-to-end

Raw Crossref được clean thành document canonical; role 3 biến `text_for_embedding` thành vector và lưu index. Test set ánh xạ mỗi câu hỏi đến DOI; evaluator so retrieved IDs và câu trả lời. Quality phát hiện lỗi nội dung/schema, freshness phát hiện dữ liệu cũ. Giữ nguyên test set/model/top-k giúp so sánh công bằng. Repair phải phục hồi document identity, quality và cả retrieval/answer metrics.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
|---|---:|---:|---:|---|
| Retrieval hit rate | 1.000 | 0.500 | 1.000 | Vector evidence suy giảm rõ nhất |
| Mean token F1 | 1.000 | 0.491 | 1.000 | Nội dung nguồn chi phối answer |
| Judge accuracy | 1.000 | 0.458 | 1.000 | Judge xác nhận degradation |
| Mean judge score | 5.000 | 2.875 | 5.000 | Repair phục hồi answer quality |
| Quality checks | 13/13 | 11/13 | 13/13 | Signal data đi trước metric |
| Freshness | fresh | stale_or_invalid | fresh | Stale data được tách khỏi relevance |

Drop latest làm một số DOI ground truth biến mất; noise/blank/truncated text đồng thời làm vector và evidence yếu, nên hit rate giảm 0.5 và F1 giảm 0.509. Khi rebuild đúng raw snapshot, cùng model/index contract tạo lại 24 documents và toàn bộ metrics trở về baseline.

## 9. Điều học được và hướng cải thiện

Tôi học được rằng collection isolation là điều kiện của phép thử; answer trace cần giàu provenance; và agent grounding phải được kiểm tra riêng với retrieval. Nếu có thêm thời gian, tôi sẽ thêm metric theo loại câu hỏi và thử hybrid retrieval/reranking, chỉ chấp nhận cải thiện khi cùng test set và latency/cost được ghi lại.

## 10. Cam kết

- [x] Báo cáo phản ánh role và artifact thực tế.
- [x] Tôi hiểu luồng end-to-end và không nhận ownership evaluation/ingestion.
- [x] Không chứa credential hoặc secret.

**Họ và tên:** Hồ Ngọc Quỳnh  
**Ngày xác nhận:** 2026-08-06
