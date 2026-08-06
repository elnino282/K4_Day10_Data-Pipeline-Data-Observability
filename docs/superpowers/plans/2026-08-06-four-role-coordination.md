# Four-Role Lab Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create four actionable Vietnamese role documents that let a four-person team complete the Data Pipeline & Data Observability lab efficiently within the prescribed four-hour timeline.

**Architecture:** Store one Markdown document per stable ownership domain under `roles/`. Each document repeats the same seven checkpoints from its own owner's perspective, while mirrored handoff contracts connect producers and consumers. A final repository-level validation checks completeness, unique ownership, path accuracy, and consistency with the approved design.

**Tech Stack:** Markdown, PowerShell, ripgrep (`rg`), Git; project context from Python modules, `README.md`, `Guide.md`, `Rubric.md`, and `phan-cong-day-10-data-pipeline-4h(2).html`.

## Global Constraints

- Write all role-document prose in Vietnamese; retain exact code identifiers and artifact paths in English.
- Use `phan-cong-day-10-data-pipeline-4h(2).html` as the canonical four-person ownership source.
- Treat the repository as an unfinished starter; use unchecked checklist items only and make no unsupported completion claims.
- Include all seven time blocks: `00:00–00:30`, `00:30–01:05`, `01:05–01:35`, `01:35–02:00`, `02:00–02:15`, `02:15–03:15`, `03:15–04:00`.
- Every handoff names the producer, consumer, artifact/contract, acceptance check, and blocker behavior.
- Do not expose `.env`, API keys, tokens, or secret values.
- Do not edit production Python code, generated artifacts under `data/`, or existing report templates as part of this plan.

---

## File Structure

- Create `roles/01-pipeline-integrator.md`: orchestration, configuration, release gates, integration and demo ownership.
- Create `roles/02-data-foundation-recovery.md`: Crossref ingestion, clean-data contract, deterministic corruption and raw-snapshot recovery ownership.
- Create `roles/03-rag-agent.md`: MiniLM, ChromaDB, retrieval, provider abstraction and agent ownership.
- Create `roles/04-evaluation-observability.md`: fixed test set, evaluation metrics, data quality, freshness and evidence-based reports ownership.
- Modify no existing files; validate all four documents against `docs/superpowers/specs/2026-08-06-four-role-coordination-design.md`.

### Task 1: Pipeline Integrator Role

**Files:**
- Create: `roles/01-pipeline-integrator.md`
- Reference: `src/core/config.py`
- Reference: `src/pipelines/phase1.py`
- Reference: `src/pipelines/corruption_flow.py`
- Reference: `script/run_phase1.py`
- Reference: `script/run_corruption_flow.py`

**Interfaces:**
- Consumes: completion evidence and artifacts from Roles 2–4 at every checkpoint.
- Produces: locked contracts, checkpoint decisions, end-to-end runs, release decision and demo sequence.

- [ ] **Step 1: Create the role header and ownership boundary**

Write the title `# Vai trò 1 — Điều phối pipeline`, mission, primary ownership for `src/core/`, `src/pipelines/`, and `script/`, and an explicit non-ownership statement for specialist implementations under `src/ingestion/`, `src/retrieval/`, `src/evaluation/`, and `src/observability/`.

- [ ] **Step 2: Add the owned file/function/artifact matrix**

The matrix must include `load_settings`, path/provider contracts, both pipeline `main()` functions, both script entrypoints, baseline/corruption release gates, and the final demo. Mark specialist artifacts as accepted inputs rather than owned outputs.

- [ ] **Step 3: Add all seven checkpoint checklists**

Include concrete actions for contract locking, raw/clean gate review, clean-to-index/test-set handoff, baseline execution, baseline freeze, corruption isolation, recovery/comparison and demo. At each checkpoint state the pass condition and what the integrator does when it fails.

- [ ] **Step 4: Add handoff and escalation tables**

Document inputs from Roles 2–4 and outputs back to the team. Require artifact path, validation command/result, pass/fail state, owner and blocker impact. State that contract changes require agreement from both producer and consumer.

- [ ] **Step 5: Add completion, verification and demo gates**

Include these commands exactly:

```powershell
rg -n "TODO\(student\)|NotImplementedError" src
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
Get-ChildItem -Recurse data\raw,data\clean,data\embeddings,data\eval,data\results,data\quality,data\reports
git grep -n -I -E "AIza|sk-[A-Za-z0-9]|API_KEY=.+"
```

The completion criteria must require artifact consistency, no state overwrite, no secret and a demo based on real outputs.

- [ ] **Step 6: Validate the document structure**

Run:

```powershell
rg -n "^## |00:00–00:30|00:30–01:05|01:05–01:35|01:35–02:00|02:00–02:15|02:15–03:15|03:15–04:00|Vai trò 2|Vai trò 3|Vai trò 4|Tiêu chí hoàn thành" roles/01-pipeline-integrator.md
```

Expected: every time block, all three partner roles and the completion section appear.

- [ ] **Step 7: Commit the role document**

```powershell
git add roles/01-pipeline-integrator.md
git commit -m "docs: add pipeline integrator role checklist"
```

### Task 2: Data Foundation and Recovery Role

**Files:**
- Create: `roles/02-data-foundation-recovery.md`
- Reference: `src/ingestion/crossref.py`
- Reference: `src/ingestion/cleaning.py`
- Reference: `src/ingestion/corruption.py`
- Reference: `src/core/config.py`
- Reference: `src/pipelines/corruption_flow.py`

**Interfaces:**
- Consumes: locked paths/settings from Role 1 and raw source/snapshot state.
- Produces: raw records, baseline/corrupted/repaired clean datasets, stable data contract and corruption log for Roles 1, 3 and 4.

- [ ] **Step 1: Create the role header and ownership boundary**

Write the title `# Vai trò 2 — Nền tảng dữ liệu & recovery`, mission, ownership for `src/ingestion/`, `data/raw/`, `data/clean/`, and `data/results/corruption_log.json`. Explain shared responsibility with Role 1 inside the orchestration file without assigning evaluation/report ownership to Role 2.

- [ ] **Step 2: Define the raw and clean contracts**

List all `PaperRecord` fields and the clean fields required by consumers. The clean handoff must include `paper_id`, `title`, `summary`, `published`, `authors_joined`, `categories_joined`, `abs_url`, `pdf_url`, `text_for_embedding`, `age_days`, and `summary_chars` with uniqueness/null expectations.

- [ ] **Step 3: Add all seven checkpoint checklists**

Cover Crossref payload persistence and retry/backoff; traceable cleaning; schema handoff; baseline lineage validation; baseline/raw snapshot freeze; deterministic/logged corruption; and repair strictly by reloading the raw snapshot and rerunning cleaning.

- [ ] **Step 4: Add producer/consumer handoff tables**

Mirror the clean schema accepted by Role 3 and Role 4. Require Role 3 to return missing-column/index errors precisely, Role 4 to return invalid-ground-truth/quality errors precisely, and Role 1 to own orchestration order. Define blocker escalation for unavailable Crossref and invalid/insufficient records.

- [ ] **Step 5: Add artifact and recovery completion checks**

List the exact raw and three-state clean artifact paths from `src/core/config.py`. Require the repaired dataset to match baseline schema, row count, canonical `paper_id` set and content derived from the same snapshot; metric recovery alone is insufficient.

- [ ] **Step 6: Add verification commands**

Include:

```powershell
rg -n "TODO\(student\)|NotImplementedError" src\ingestion src\pipelines\corruption_flow.py
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
Get-ChildItem data\raw,data\clean,data\results
Get-Content -Raw data\results\corruption_log.json | ConvertFrom-Json
```

State expected artifact invariants rather than claiming current success.

- [ ] **Step 7: Validate and commit the document**

```powershell
rg -n "^## |PaperRecord|text_for_embedding|age_days|summary_chars|raw snapshot|corruption_log|Vai trò 1|Vai trò 3|Vai trò 4|00:00–00:30|03:15–04:00" roles/02-data-foundation-recovery.md
git add roles/02-data-foundation-recovery.md
git commit -m "docs: add data foundation recovery role checklist"
```

### Task 3: RAG and Agent Role

**Files:**
- Create: `roles/03-rag-agent.md`
- Reference: `src/retrieval/embeddings.py`
- Reference: `src/retrieval/index.py`
- Reference: `src/retrieval/llm.py`
- Reference: `src/retrieval/agent.py`
- Reference: `src/retrieval/qa.py`
- Reference: `src/core/config.py`

**Interfaces:**
- Consumes: validated baseline/corrupted/repaired DataFrames from Role 2 and fixed configuration from Role 1.
- Produces: three isolated Chroma collections/manifests, retrieval evidence and agent smoke-test evidence for Roles 1 and 4.

- [ ] **Step 1: Create the role header and ownership boundary**

Write the title `# Vai trò 3 — RAG & agent`, mission and ownership for `src/retrieval/`, `data/chroma/`, `data/embeddings/`, and `data/results/agent_demo_answers.json`. State that test-set construction and metric interpretation belong to Role 4.

- [ ] **Step 2: Define the index and provider contracts**

List the nine DataFrame fields consumed by `LocalEmbeddingIndex._build_documents()`, the `search()`/`lookup()` output expectations, the fixed MiniLM model, `top_k`, three collection names and supported LLM providers. Include the rule that no credentials appear in source, logs or reports.

- [ ] **Step 3: Add all seven checkpoint checklists**

Cover contract inspection, text validation, baseline collection/search/lookup/agent smoke tests, baseline evidence freeze, separate corrupted collection, separate repaired collection, and same-query comparison for the demo.

- [ ] **Step 4: Add mirrored handoffs**

Accept the Role 2 schema and report exact contract failures. Return manifest path, collection, model, count, retrieved IDs and contexts to Roles 1 and 4. Require Role 4 ground-truth IDs to exist in the index and clarify that `metrics.py` evaluates the QA helper rather than the LangChain agent directly.

- [ ] **Step 5: Add risk controls and completion criteria**

Include first-run model download, provider/Ollama availability, empty/small corpus, `top_k` greater than document count, duplicate lookup overwrite, agent content blocks and evaluator/agent scope mismatch. Give each risk a detection method and response.

- [ ] **Step 6: Add verification commands**

Include artifact listing plus the index and agent smoke commands documented in the approved design context. Mark agent smoke as credential/provider-dependent while index search/lookup remains mandatory.

- [ ] **Step 7: Validate and commit the document**

```powershell
rg -n "^## |MiniLM|Chroma|papers-baseline|papers-corrupted|papers-repaired|semantic|lookup|agent|Vai trò 1|Vai trò 2|Vai trò 4|00:00–00:30|03:15–04:00" roles/03-rag-agent.md
git add roles/03-rag-agent.md
git commit -m "docs: add RAG agent role checklist"
```

### Task 4: Evaluation and Observability Role

**Files:**
- Create: `roles/04-evaluation-observability.md`
- Reference: `src/evaluation/testset.py`
- Reference: `src/evaluation/metrics.py`
- Reference: `src/observability/quality.py`
- Reference: `src/observability/reporting.py`
- Reference: `src/core/config.py`

**Interfaces:**
- Consumes: clean contract from Role 2, three indexes/retrieval evidence from Role 3 and orchestration paths/gates from Role 1.
- Produces: one fixed test set, three-state answers/metrics, quality/freshness evidence and phase/comparison reports.

- [ ] **Step 1: Create the role header and ownership boundary**

Write the title `# Vai trò 4 — Evaluation & observability`, mission and ownership for `src/evaluation/`, `src/observability/`, `data/eval/`, evaluation outputs under `data/results/`, `data/quality/`, and pipeline-generated reports under `data/reports/`. Exclude data repair and index implementation.

- [ ] **Step 2: Define test-set and evaluation contracts**

Require `id`, `question_type`, `question`, `ground_truth`, and `ground_truth_doc_ids`; include summary/authors/date/categories question types and real clean `paper_id` values. State that the same test-set artifact, evaluator, model and `top_k` are reused for all states.

- [ ] **Step 3: Define observability and report contracts**

List row count, ID null/unique, title/summary completeness, duplicate, date/`age_days`, freshness bounds and status. Require per-state artifact naming to avoid the single `freshness_report` path overwrite risk. Reports must derive values from artifacts and show baseline/corrupted/repaired deltas.

- [ ] **Step 4: Add all seven checkpoint checklists**

Cover test design, baseline quality input, test-set/index consistency, baseline evaluation/report, baseline freeze, corrupted evaluation/quality/freshness, repaired evaluation and evidence-based comparison.

- [ ] **Step 5: Add mirrored handoffs and blocker behavior**

Accept schema and IDs from Role 2, index/manifests and retrieval contexts from Role 3, and path/run order from Role 1. Return test-set hash/path, metrics, quality/freshness reports and comparison conclusions. Escalate empty test set, missing IDs, judge fallback, Ragas errors and overwritten freshness outputs explicitly.

- [ ] **Step 6: Add completion and verification commands**

Include:

```powershell
rg -n "TODO\(student\)|NotImplementedError" src\evaluation src\observability
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
Get-Content -Raw data\eval\test_set.json | ConvertFrom-Json
Get-Content -Raw data\results\baseline_metrics.json | ConvertFrom-Json
Get-Content -Raw data\results\corrupted_metrics.json | ConvertFrom-Json
Get-Content -Raw data\results\repaired_metrics.json | ConvertFrom-Json
Get-ChildItem -Recurse data\quality,data\reports
```

Require at least one inspected retrieval hit/miss and two evidence chains: corruption impact and repair outcome.

- [ ] **Step 7: Validate and commit the document**

```powershell
rg -n "^## |ground_truth_doc_ids|retrieval_hit_rate|mean_token_f1|judge_accuracy|mean_judge_score|freshness|fallback|Ragas|Vai trò 1|Vai trò 2|Vai trò 3|00:00–00:30|03:15–04:00" roles/04-evaluation-observability.md
git add roles/04-evaluation-observability.md
git commit -m "docs: add evaluation observability role checklist"
```

### Task 5: Cross-Role Consistency and Final Verification

**Files:**
- Verify: `roles/01-pipeline-integrator.md`
- Verify: `roles/02-data-foundation-recovery.md`
- Verify: `roles/03-rag-agent.md`
- Verify: `roles/04-evaluation-observability.md`
- Reference: `docs/superpowers/specs/2026-08-06-four-role-coordination-design.md`

**Interfaces:**
- Consumes: the four completed role documents.
- Produces: a consistent, navigable role pack with no missing checkpoint or ambiguous artifact ownership.

- [ ] **Step 1: Confirm the exact file set**

```powershell
Get-ChildItem roles -File | Select-Object -ExpandProperty Name
```

Expected exactly:

```text
01-pipeline-integrator.md
02-data-foundation-recovery.md
03-rag-agent.md
04-evaluation-observability.md
```

- [ ] **Step 2: Scan for incomplete content**

```powershell
rg -n -i "TBD|TODO|implement later|fill in|placeholder|\[Tên|\[Mô tả|\[Đường dẫn" roles
```

Expected: no matches. Unchecked task markers `- [ ]` are intentional and must remain.

- [ ] **Step 3: Verify all checkpoint occurrences**

```powershell
$times = @('00:00–00:30','00:30–01:05','01:05–01:35','01:35–02:00','02:00–02:15','02:15–03:15','03:15–04:00')
Get-ChildItem roles -File | ForEach-Object {
  $content = Get-Content -Raw -LiteralPath $_.FullName
  foreach ($time in $times) {
    if (-not $content.Contains($time)) { throw "Missing $time in $($_.Name)" }
  }
}
```

Expected: exit code 0 with no missing-time exception.

- [ ] **Step 4: Verify mirrored handoff contracts**

Manually compare these producer/consumer pairs:

- Role 2 clean schema → Role 3 index input.
- Role 2 IDs/quality fields → Role 4 test-set and observability input.
- Role 3 manifests/retrieved IDs/contexts → Role 4 evaluation input.
- Roles 2–4 evidence → Role 1 release gate input.

Expected: names, paths, acceptance criteria and blocker behavior match on both sides.

- [ ] **Step 5: Verify repository paths and identifiers**

```powershell
rg -o '`(src|script|data)/[^`]+`' roles | Sort-Object -Unique
rg -n "class Paths|def load_settings|def build_clean_dataframe|class LocalEmbeddingIndex|def build_test_set|def evaluate_pipeline|def run_data_quality_checks|def generate_phase1_report" src
```

Expected: every documented path/identifier is present in the starter or explicitly described as a generated artifact from `src/core/config.py`.

- [ ] **Step 6: Run Markdown diff checks**

```powershell
git diff --check
git diff --stat
```

Expected: no whitespace errors; only the four role files are new in the implementation diff.

- [ ] **Step 7: Commit any consistency corrections**

If Task 5 requires corrections, commit only those corrections:

```powershell
git add roles
git commit -m "docs: align cross-role handoff contracts"
```

If no corrections are needed, do not create an empty commit.
