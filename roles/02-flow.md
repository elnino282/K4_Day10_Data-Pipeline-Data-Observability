# Vai trò 2 — Flow thực thi và handoff

## A. Các bước của Vai trò 2

```mermaid
flowchart TD
    S0["0. Chốt endpoint/query/filter<br/>với Vai trò 1"]:::gate
    S1["1. fetch_source_records()<br/>crossref.py:36 + parse_crossref_payload()"]
    A1[("data/raw/crossref_response.json<br/>data/raw/crossref_records.json")]:::art
    S2["2. build_clean_dataframe()<br/>cleaning.py:10"]
    A2[("data/clean/papers_clean.csv + .json<br/>= BASELINE")]:::art
    S3["3. FREEZE baseline<br/>công bố schema, row count,<br/>tập/hash paper_id, run_date, path"]:::gate
    S4["4. Chốt seed + rule corruption<br/>với Vai trò 1"]:::gate
    S5["5. corrupt_clean_dataframe()<br/>corruption.py:6"]
    A3[("papers_clean_corrupted.csv + .json<br/>data/results/corruption_log.json")]:::art
    S6["6. load_raw_records()<br/>crossref.py:49 — reload raw snapshot"]
    S7["7. Rerun ĐÚNG cleaning rule cũ<br/>+ ĐÚNG run_date cũ"]
    A4[("papers_clean_repaired.csv + .json")]:::art
    S8{"8. repaired == baseline?<br/>schema · row count · tập paper_id<br/>· canonical content · cùng test set"}
    S9["9. Release / demo"]:::ok
    SX["Blocker: KHÔNG vá tay.<br/>Quay lại raw snapshot"]:::bad

    S0 --> S1 --> A1 --> S2 --> A2 --> S3 --> S4 --> S5 --> A3
    A3 --> S6 --> S7 --> A4 --> S8
    S8 -- "đạt" --> S9
    S8 -- "lệch" --> SX --> S6
    A1 -. "nguồn recovery duy nhất" .-> S6

    classDef gate fill:#4a3800,stroke:#c99a00,color:#ffe08a
    classDef art fill:#0d3050,stroke:#3d8fd1,color:#cfe6ff
    classDef ok fill:#0f3d20,stroke:#3fa15c,color:#c9f2d6
    classDef bad fill:#4a1010,stroke:#c94a4a,color:#ffd0d0
```

## B. Input vào / Output ra các vai trò khác

```mermaid
flowchart LR
    subgraph R1["Vai trò 1 — Pipeline Integrator"]
        R1a["endpoint/query/filter đã chốt"]
        R1b["seed + mutation plan<br/>+ yêu cầu rebuild corruption_flow.py"]
        R1c["build/rebuild index"]
    end

    subgraph R2["VAI TRÒ 2 — BẠN"]
        direction TB
        F["fetch + parse<br/>crossref.py"]
        C["cleaning<br/>cleaning.py"]
        X["corruption<br/>corruption.py"]
        V["recovery + đối chiếu"]
        F --> C --> X --> V
    end

    subgraph R3["Vai trò 3 — RAG Agent"]
        R3a["quality/freshness/schema finding"]
        R3b["retrieval + agent"]
    end

    subgraph R4["Vai trò 4 — Evaluation & Observability"]
        R4a["acceptance / sai lệch artifact"]
        R4b["metrics + report"]
    end

    R1a ==> F
    R1b ==> X
    C == "raw snapshot + baseline clean contract" ==> R1c
    C == "3 trạng thái clean + provenance + corruption_log" ==> R3b
    C == "clean contract + baseline freeze + recovery criteria" ==> R4b
    X == "corrupted artifact + seed/rule log" ==> R1c

    R3a -. "chặn release · rerun cleaning từ raw" .-> V
    R4a -. "chặn handoff · tái tạo từ snapshot" .-> V
```

## C. Bảng handoff rút gọn

| Hướng | Bạn nhận / gửi gì | Accept khi đối tác trả lời đúng | Nếu fail |
| --- | --- | --- | --- |
| Vai trò 1 → 2 | endpoint, query, filter | URL + params xác định | Chặn fetch |
| Vai trò 1 → 2 | seed, mutation plan, target | seed, target, log fields | Chặn mutation, không tự đoán rule |
| 2 → Vai trò 1 | raw snapshot + baseline CSV/JSON | schema, row count, tập `paper_id`, run_date, path | Dừng build index, phát hành snapshot mới có provenance |
| 2 → Vai trò 3 | 3 trạng thái clean + corruption log | schema, row count, tập `paper_id`, path | Dừng quality check |
| Vai trò 3 → 2 | schema/freshness/quality finding | artifact, rule tái lập, recovery source | Dừng release, reload raw + rerun cleaning |
| 2 → Vai trò 4 | clean contract, baseline freeze, recovery criteria | schema, row count, `paper_id`, canonical check, cùng test set | Dừng demo/release |
| Vai trò 4 → 2 | acceptance result, sai lệch artifact | snapshot, run_date, corruption log, trạng thái re-clean | Dừng handoff, tái tạo từ raw + accept lại |

## D. Clean contract — 11 cột bắt buộc

`paper_id` · `title` · `summary` · `published` · `authors_joined` · `categories_joined` · `abs_url` · `pdf_url` · `text_for_embedding` · `age_days` · `summary_chars`

`paper_id` là khóa ổn định (DOI). `text_for_embedding` sinh deterministic từ nội dung canonical đã clean.

## E. Luật cứng

- Không sửa tay file corrupted.
- Không copy baseline rồi gọi là repaired.
- Repaired chỉ được sinh bằng cách reload `data/raw/crossref_records.json` và rerun cleaning.
- Metric recovery một mình KHÔNG đủ để accept — phải đối chiếu đủ 5 tiêu chí ở bước 8.
- Không ghi secret vào artifact hay log.
