# Vai trò 3 — RAG & agent

## Mục tiêu và phạm vi sở hữu

Vai trò 3 chịu trách nhiệm biến cleaned dataset thành các vector index tách biệt, cung cấp semantic search/exact lookup, cấu hình agent dùng công cụ truy xuất và bàn giao bằng chứng kỹ thuật để các vai trò khác đánh giá, tích hợp và báo cáo.

**Ownership chính:**

- `src/retrieval/`: embedding, ChromaDB index, search, lookup, LLM provider abstraction và LangChain agent.
- `data/chroma/`: persistent vector store.
- `data/embeddings/`: manifest của baseline, corrupted và repaired index.
- `data/results/agent_demo_answers.json`: câu trả lời demo của agent khi pipeline tạo artifact này.

**Không thuộc ownership của Vai trò 3:**

- Cleaning và định nghĩa clean schema.
- Xây dựng evaluation test set và ground truth.
- Diễn giải metrics, quality/freshness hoặc viết báo cáo kết quả.
- Orchestration trong `src/pipelines/` và các entrypoint trong `script/`.

Vai trò 3 phát hiện lỗi contract và trả lại bằng chứng chính xác cho owner tương ứng; không tự sửa module ngoài phạm vi để che lỗi tích hợp.

## Contract kỹ thuật phải khóa

### Clean DataFrame đầu vào

`LocalEmbeddingIndex._build_documents()` cần đủ chín field sau:

1. `paper_id`
2. `title`
3. `text_for_embedding`
4. `published`
5. `authors_joined`
6. `categories_joined`
7. `summary`
8. `abs_url`
9. `pdf_url`

Điều kiện nhận: các field tồn tại; `paper_id`, `title` và `text_for_embedding` không rỗng; `paper_id` ổn định; duplicate được xử lý hoặc được báo rõ; nội dung embedding phản ánh title/summary thật.

### Embedding, collection và retrieval

- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` qua `MiniLMEmbeddings`, vector được normalize.
- Retrieval mặc định: `top_k=4`.
- Collection bắt buộc tách biệt:
  - Baseline: `papers-baseline`.
  - Corrupted: `papers-corrupted`.
  - Repaired: `papers-repaired`.
- `search(query, top_k) -> list[SearchResult]`: mỗi kết quả có `paper_id`, `title`, `score`, `content`, `metadata`; `retrieved_doc_ids` và contexts phải truy vết được về corpus tương ứng.
- `lookup(value) -> dict | None`: exact lookup theo `paper_id` hoặc exact title sau khi trim/lowercase; trả document đã index hoặc `None`.
- Mỗi manifest phải ghi đúng backend, embedding model, persist path, collection name và documents của trạng thái đó.

### Agent và provider

`build_llm()` hỗ trợ Gemini, OpenAI, Anthropic, OpenRouter, Ollama và custom OpenAI-compatible endpoint. Agent phải dùng `semantic_search_papers` hoặc `lookup_paper` trước khi trả lời câu hỏi factual và phải nói rõ khi corpus không hỗ trợ câu trả lời.

API key chỉ nằm trong `.env` cục bộ hoặc secret store, không xuất hiện trong source, lệnh, log, manifest, answers hay report. Agent smoke phụ thuộc provider/credential hợp lệ; riêng Ollama còn phụ thuộc server/model đang chạy.

## Kế hoạch theo bảy mốc

### 00:00–00:30 — Đọc contract và chuẩn bị kiểm tra

- [ ] Đọc `src/retrieval/embeddings.py`, `index.py`, `llm.py`, `agent.py`, `qa.py` và các giá trị liên quan trong `src/core/config.py`.
- [ ] Xác nhận chín field đầu vào, MiniLM, `top_k=4`, ba collection name và bốn artifact thuộc ownership.
- [ ] Thống nhất với Vai trò 2 cách báo lỗi thiếu field, null, duplicate và `text_for_embedding` không hợp lệ; báo Vai trò 1 nếu lỗi chặn tích hợp.
- [ ] Chuẩn bị một semantic query, một exact lookup và một factual agent question có thể kiểm chứng.

### 00:30–01:05 — Kiểm tra text và metadata trước index

- [ ] Đọc mẫu `text_for_embedding` thật; xác nhận có nội dung hữu ích, không rỗng và không lặp vô ích.
- [ ] Kiểm tra `paper_id`, title và metadata cần thiết tồn tại trước khi nhận handoff.
- [ ] Trả contract failure chính xác cho Vai trò 2 nếu schema/content không đạt và thông báo Vai trò 1 về blocker tích hợp; không build collection final từ input lỗi.

### 01:05–01:35 — Baseline index và agent smoke

- [ ] Build MiniLM embeddings và collection `papers-baseline` từ cleaned dataset đã accept.
- [ ] Kiểm tra manifest baseline, collection name và document count khớp input.
- [ ] Chạy semantic search và xác minh IDs/contexts có nguồn.
- [ ] Chạy exact lookup bằng một `paper_id` và một title đã biết.
- [ ] Build agent và chạy factual smoke khi provider/credential sẵn sàng; xác minh agent dùng tool.
- [ ] Ghi blocker rõ ràng nếu model/provider không sẵn sàng; không ghi nhận smoke là pass giả.

### 01:35–02:00 — Khóa bằng chứng baseline

- [ ] Bàn giao cho Vai trò 1 manifest path, collection, model, count và kết quả smoke baseline để tích hợp.
- [ ] Bàn giao cho Vai trò 4 retrieved IDs/contexts để kiểm tra ground-truth document IDs và evaluation contract.
- [ ] Freeze query mẫu và cấu hình retrieval dùng để so sánh ba trạng thái.
- [ ] Xác nhận baseline collection vẫn load/search được trước khi corruption flow bắt đầu.

### 02:00–02:15 — Nghỉ và chuẩn bị so sánh

- [ ] Ghi lại blocker còn mở và vị trí evidence baseline trước khi nghỉ.
- [ ] Sau nghỉ, xác nhận sẽ giữ nguyên query, embedding model và `top_k` khi so sánh.

### 02:15–03:15 — Corrupted collection và cùng-query comparison

- [ ] Nhận corrupted DataFrame cùng schema đã khóa từ Vai trò 2 và build riêng `papers-corrupted`.
- [ ] Xác nhận corrupted manifest/path không ghi đè baseline.
- [ ] Chạy lại đúng semantic query/exact lookup baseline với cùng `top_k=4`.
- [ ] Bàn giao retrieved IDs/contexts baseline–corrupted cho Vai trò 4; chỉ mô tả thay đổi quan sát được, không tự diễn giải metric.
- [ ] Kiểm tra `papers-baseline` vẫn load/search được và không bị mutate.

### 03:15–04:00 — Repaired collection, demo và release check

- [ ] Nhận repaired DataFrame được Vai trò 2 tạo lại từ raw/source đáng tin và build riêng `papers-repaired`.
- [ ] Xác nhận repaired manifest/path/count và ba collection đều tồn tại độc lập.
- [ ] Chạy cùng query trên baseline, corrupted và repaired với cùng model/`top_k`.
- [ ] Chạy agent smoke trên repaired index khi provider/credential hợp lệ.
- [ ] Bàn giao retrieved IDs/contexts và query evidence cho Vai trò 4; bàn giao manifest/model/count cùng release blocker cho Vai trò 1; ghi rõ mọi recovery chưa được chứng minh.
- [ ] Hoàn tất checklist demo/release của vai trò bên dưới.

## Handoff bắt buộc

| Handoff | Producer | Consumer | Artifact/contract | Cách accept | Blocker behavior |
|---|---|---|---|---|---|
| Clean schema → RAG | Vai trò 2 | Vai trò 3 | Clean DataFrame/CSV/JSON có đủ chín field; `paper_id` ổn định; `text_for_embedding` hợp lệ | Kiểm tra field, null, duplicate, sample text và count trước build | Dừng build; gửi field/row/count lỗi chính xác và sample đã che dữ liệu nhạy cảm cho Vai trò 2, đồng thời báo blocker tích hợp cho Vai trò 1; không tự sửa cleaning |
| Settings → RAG | Vai trò 1 | Vai trò 3 | `Settings`: paths, model, `top_k`, ba collection và provider config | Đối chiếu với `src/core/config.py`; không có secret trong output | Dừng bước phụ thuộc cấu hình; báo đúng setting/path/provider thiếu hoặc sai cho Vai trò 1; không hard-code |
| Evaluation contract → RAG | Vai trò 4 | Vai trò 3 | Câu hỏi cố định và `ground_truth_doc_ids` dùng để kiểm tra retrieval | Mọi ground-truth ID cần kiểm chứng đều tồn tại trong index baseline hoặc được báo là contract failure | Trả danh sách ID/query không đối chiếu được cho Vai trò 4 và báo Vai trò 1 nếu chặn tích hợp; không sửa test set hoặc ground truth |
| Hit/miss evidence → RAG analysis | Vai trò 4 | Vai trò 3 | Artifact gồm chính xác `question`, expected/ground-truth IDs, retrieved IDs, contexts và config của state: collection, embedding model, `top_k`, test-set path/hash | Các field ID/config/context hiện diện và đúng kiểu; expected IDs khớp baseline contract đã khóa; collection/model/`top_k`/test-set hash đúng state; retrieved IDs và contexts đối chiếu được, kể cả trường hợp miss được biểu diễn rõ | Nếu field/expected ID không hợp lệ ở baseline hoặc config lệch contract thì dừng phân tích, trả mismatch chính xác cho Vai trò 4 và báo Vai trò 1. Nếu expected ID chỉ vắng ở corrupted/repaired do corruption hoặc recovery failure, ghi đó là degradation/recovery evidence và vẫn tiếp tục evaluation/analysis bằng test set đã khóa |
| RAG evidence → Evaluation | Vai trò 3 | Vai trò 4 | Collection/model/count, retrieved IDs, contexts, scores và manifest path | Vai trò 4 đọc được artifact và truy vết mỗi ID/context về đúng collection | Báo exact query, collection, exception hoặc output rỗng; không diễn giải metric thay Vai trò 4 |
| RAG artifacts → Integration | Vai trò 3 | Vai trò 1 | Ba manifest path, collection names, model, counts; load/search/lookup contract | Vai trò 1 load đúng manifest, gọi được API và xác nhận không ghi đè trạng thái khác | Gửi contract failure với path, collection, expected/actual và bước tái hiện cho Vai trò 1; không sửa orchestration |
| Demo evidence → Release | Vai trò 3 | Vai trò 1 | `data/results/agent_demo_answers.json` nếu được tạo, cùng provider/model không chứa secret | Artifact đọc được, câu trả lời gắn với tool/retrieval evidence và trạng thái chạy được ghi trung thực | Nếu credential/provider thiếu, đánh dấu chưa chạy và bàn giao blocker cho Vai trò 1; không tạo answer giả |

## Ranh giới giữa evaluator và LangChain agent

`src/evaluation/metrics.py` gọi `retrieval.qa.answer_question()` để tạo answers và metrics. Hàm này dùng retrieval cùng logic trích xuất theo quy tắc; nó **không trực tiếp chạy LangChain agent** được tạo bởi `src/retrieval/agent.py`. Vì vậy:

- Metrics hiện tại là bằng chứng cho retrieval/QA path, không tự động chứng minh agent đã gọi tool đúng.
- Agent cần smoke evidence riêng.
- Không được dùng kết quả evaluator để tuyên bố LangChain agent đã pass nếu chưa chạy agent smoke.

## Rủi ro và ứng phó

| Rủi ro | Owner xử lý chính | Cách phát hiện | Response |
|---|---|---|---|
| MiniLM phải tải model lần đầu | Vai trò 3, phối hợp Vai trò 1 về môi trường | Lỗi download/cache/network khi khởi tạo `MiniLMEmbeddings` | Ghi nguyên nhân và lệnh tái hiện đã che thông tin; bàn giao blocker môi trường cho Vai trò 1, không thay model âm thầm |
| Provider credential thiếu hoặc Ollama chưa chạy/chưa có model | Vai trò 3, phối hợp Vai trò 1 | `build_llm()`/agent invoke báo credential, connection hoặc model error | Giữ lỗi làm blocker; gửi lỗi provider đã che secret cho Vai trò 1; không log key và không ghi agent smoke pass |
| Corpus rỗng hoặc quá nhỏ | Vai trò 2 sửa dữ liệu; Vai trò 3 phát hiện | DataFrame count bằng 0/nhỏ, embed/query lỗi hoặc kết quả không đủ | Dừng build/evaluation; trả count và contract failure cho Vai trò 2, đồng thời báo Vai trò 1 và 4 |
| `top_k` lớn hơn document count hoặc khác giữa ba trạng thái | Vai trò 3 | So sánh `top_k=4` với count; Chroma query lỗi; settings/query khác nhau | Báo blocker và thống nhất chính sách có kiểm soát; giữ cùng cấu hình khi comparison, không thay đổi âm thầm |
| Duplicate `paper_id`/title làm lookup ghi đè | Vai trò 2 sửa dữ liệu; Vai trò 3 phát hiện | So sánh unique count với row count; lookup trả document không kỳ vọng | Dừng accept; trả duplicate IDs/titles và count cho Vai trò 2, báo Vai trò 1 nếu chặn tích hợp |
| Provider trả agent content dạng blocks/list thay vì chuỗi | Vai trò 3 | Kiểm tra kiểu `final_message.content` và serialization của demo answers | Chuẩn hóa/serialize trong phạm vi retrieval nếu được giao thay đổi code; trước đó ghi contract failure chính xác |
| Evaluator/agent mismatch | Vai trò 4 và 3 | Đối chiếu call path: `metrics.py` → `qa.answer_question()`, không qua `build_agent()` | Vai trò 4 và 3 bàn giao hai evidence riêng; không suy diễn agent quality từ evaluator metrics |

## Lệnh kiểm chứng dự kiến

Các lệnh chỉ chạy sau khi owner upstream đã tạo artifact cần thiết.

Kiểm tra artifact và collection files:

```powershell
Get-ChildItem data\embeddings -File
Get-ChildItem data\chroma -Force
Get-ChildItem data\results\agent_demo_answers.json -ErrorAction SilentlyContinue
```

Index smoke baseline:

```powershell
uv run python -c "from core.config import load_settings; from retrieval.index import LocalEmbeddingIndex; s=load_settings(); i=LocalEmbeddingIndex.load(s); assert s.top_k == 4, f'Expected top_k=4, got {s.top_k}'; assert len(i.documents) >= s.top_k, f'Corpus has {len(i.documents)} documents, fewer than top_k={s.top_k}'; print(i.collection_name, len(i.documents)); print(i.search('retrieval augmented generation', top_k=s.top_k)); print(i.lookup(i.documents[0]['paper_id']))"
```

Agent smoke — chỉ chạy khi provider/credential hợp lệ hoặc Ollama server/model đã sẵn sàng:

```powershell
uv run python -c "from core.config import load_settings; from retrieval.index import LocalEmbeddingIndex; from retrieval.agent import build_agent,run_agent_question; s=load_settings(); i=LocalEmbeddingIndex.load(s); print(run_agent_question(build_agent(s,i),'What is one indexed paper about?'))"
```

Kiểm tra cấu hình collection và các stub có thể chặn tích hợp:

```powershell
rg -n "papers-baseline|papers-corrupted|papers-repaired|top_k|embedding_model" src/core/config.py src/retrieval
rg -n "TODO\(student\)|NotImplementedError" src
```

## Checklist demo/release riêng cho Vai trò 3

- [ ] Ba manifest trỏ đúng ba collection và document count tương ứng.
- [ ] `papers-baseline` không bị ghi đè khi build corrupted/repaired.
- [ ] Cùng query, embedding model và `top_k` được dùng cho ba trạng thái.
- [ ] Có semantic search evidence và exact lookup evidence truy vết được.
- [ ] Có agent-tool smoke evidence, hoặc blocker credential/provider được ghi trung thực.
- [ ] Retrieved IDs/contexts đã bàn giao cho Vai trò 4; manifest/model/count đã bàn giao cho Vai trò 1.
- [ ] Demo phân biệt rõ evaluator QA path với LangChain agent path.
- [ ] Không có secret trong source, lệnh, log, manifest, answers hoặc báo cáo.
- [ ] Không tuyên bố metrics/recovery thành công nếu Vai trò 4 chưa xác minh từ artifact thật và Vai trò 1 chưa accept release contract.
