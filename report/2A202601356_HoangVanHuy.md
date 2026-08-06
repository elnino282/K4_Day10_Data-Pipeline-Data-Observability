# Individual Report - Role 4: Corruption & Integration Owner

## 1. Thong tin ca nhan

| Thong tin | Noi dung |
|---|---|
| Ho va ten | Hoang Van Huy |
| MSSV | 2A202601356 |
| Khoa/Lop | K4 |
| Ten nhom | K4 Day 10 - Data Pipeline & Observability |
| Vai tro chinh | Role 4 - Corruption & Integration owner |
| Repository | `K4_Day10_Data-Pipeline-Data-Observability` |
| Ngay hoan thanh | 2026-08-06 |

## 2. Vai tro va pham vi cong viec

### Phan viec so huu

| Module/deliverable | File/ham phu trach | Input nhan vao | Output ban giao | Trang thai |
|---|---|---|---|---|
| Tao corruption co kiem soat | `src/ingestion/corruption.py`, `corrupt_clean_dataframe` | Baseline clean dataframe | Corrupted dataframe va `data/results/corruption_log.json` | Hoan thanh |
| Chay flow baseline -> corrupted -> repaired | `src/pipelines/corruption_flow.py` | Raw snapshot, clean baseline, test set, baseline metrics | `corrupted_*`, `repaired_*`, `comparison_metrics.json`, `corruption_report.md` | Hoan thanh |
| Kiem tra repair | `_assert_repaired_matches_baseline`, `repair_validation` | Baseline dataframe va repaired dataframe | Xac nhan document identity/content duoc phuc hoi | Hoan thanh |
| Bao cao tac dong len RAG | `data/reports/corruption_report.md`, `data/results/comparison_metrics.json` | Metrics va quality/freshness cua 3 trang thai | Bang so sanh baseline/corrupted/repaired | Hoan thanh |

### Viec ho tro ngoai pham vi chinh

| Hoat dong | Thanh vien/module duoc ho tro | Ket qua |
|---|---|---|
| Kiem tra artifact truoc khi corruption flow chay | Ingestion, cleaning, evaluation-set owner | Flow chi tiep tuc khi raw, clean, embeddings, test set va baseline report da ton tai |
| Giu evaluation set co dinh | Evaluation owner | Baseline, corrupted va repaired dung cung `data/eval/test_set.json` de so sanh cong bang |
| Noi observability vao integration flow | Observability owner | Moi trang thai corrupted/repaired deu co quality va freshness artifacts rieng |

## 3. Ket qua theo vai tro

| Nhiem vu da thuc hien | File/ham/artifact lien quan | Ket qua ban giao | Cach xac minh |
|---|---|---|---|
| Ap dung 6 corruption scenario co log | `src/ingestion/corruption.py`, `data/results/corruption_log.json` | Drop latest, blank summary, summary noise, truncate title, stale date, duplicate rows | Doc log va chay `uv run python -m pytest tests/test_corruption.py -q` |
| Danh gia corrupted state bang cung test set | `src/pipelines/corruption_flow.py`, `data/results/corrupted_metrics.json` | `retrieval_hit_rate=0.500`, `mean_token_f1=0.491`, `judge_accuracy=0.458`, `mean_judge_score=2.875` | Doi chieu `data/results/comparison_metrics.json` |
| Repair bang cach rebuild tu raw snapshot | `load_raw_records`, `build_clean_dataframe`, `_assert_repaired_matches_baseline` | Repaired phuc hoi 24/24 ID va canonical content | `repair_validation.document_identity_restored=true` |
| Tao bao cao so sanh ba trang thai | `data/reports/corruption_report.md` | Report neu ro delta corruption va delta repair | Mo report va so voi `comparison_metrics.json` |

Artifact quan trong nhat cua role 4 la `data/results/comparison_metrics.json`, vi file nay ket noi truc tiep giua thay doi du lieu, tin hieu observability va tac dong len RAG metrics.

## 4. Giai thich phan ky thuat da thuc hien

### Van de can giai quyet

Pipeline RAG co the cho ket qua sai khong phai vi model kem, ma vi corpus/index bi hong: mat tai lieu moi, summary rong, title bi cat, ngay xuat ban cu hoac duplicate document ID. Role 4 tao mot flow co the tai hien cac loi do, do tac dong len agent, sau do repair va chung minh ket qua phuc hoi tren cung evaluation set.

### Cach trien khai

`corrupt_clean_dataframe` nhan clean dataframe, sap xep theo `published` moi nhat truoc va ap dung cac mutation deterministic. Ham khong dung random seed de ket qua lap lai duoc. Moi scenario ghi `scenario`, `affected_count` va danh sach `paper_ids` vao `corruption_log.json`.

Trong `corruption_flow.py`, baseline artifacts duoc khoa bang hash trong `baseline_manifest.json`. Truoc khi corrupt, flow xac minh raw response, raw records, clean CSV/JSON, embedding manifest, test set, baseline metrics, quality/freshness va report. Sau khi corrupt va repair, flow kiem tra lai hash cua cac artifact baseline de dam bao khong vo tinh ghi de baseline.

Repair khong sua truc tiep tren corrupted rows. Flow doc lai `data/raw/crossref_records.json`, chay lai `build_clean_dataframe` voi cung `run_date_utc`, roi so sanh schema, row count, set `paper_id` va canonical content voi baseline. Cach nay chung minh repair la rebuild tu nguon raw dang tin cay.

### Input, output va contract

| Thanh phan | Mo ta |
|---|---|
| Input | `data/clean/papers_clean.json`, `data/raw/crossref_records.json`, `data/eval/test_set.json`, baseline metrics/quality/freshness |
| Output | `papers_clean_corrupted.*`, `papers_clean_repaired.*`, `corruption_log.json`, `corrupted_metrics.json`, `repaired_metrics.json`, `comparison_metrics.json`, `corruption_report.md` |
| Module phu thuoc | `ingestion.cleaning`, `ingestion.crossref`, `retrieval.index`, `evaluation.metrics`, `observability.quality`, `observability.reporting` |
| Module su dung output | Report chung, UI/report viewer, nguoi cham bai doi chieu artifact |
| Dieu kien loi can xu ly | Thieu baseline lock, schema corrupted bi lech, repaired content khong khop baseline, baseline artifact bi thay doi trong luc chay |

### Cach xac minh

```powershell
uv run python script/run_corruption_flow.py
uv run python -m pytest -q
```

- Ket qua mong doi: corrupted metrics giam, quality/freshness bao loi, repaired metrics va document identity phuc hoi ve baseline.
- Ket qua thuc te: corrupted `retrieval_hit_rate=0.500`, repaired `retrieval_hit_rate=1.000`; quality tu 13/13 -> 11/13 -> 13/13; freshness tu `fresh` -> `stale_or_invalid` -> `fresh`.
- Artifact/log: `data/results/comparison_metrics.json`, `data/results/corruption_log.json`, `data/quality/*`, `data/reports/corruption_report.md`.

## 5. Mot quyet dinh ky thuat quan trong

- Boi canh: Can repair dataset sau corruption nhung van phai chung minh du lieu da tro ve dung baseline.
- Cac phuong an da can nhac: sua truc tiep corrupted rows theo log, hoac rebuild lai clean data tu raw snapshot da khoa hash.
- Phuong an da chon: rebuild tu normalized raw snapshot.
- Ly do: cach nay tranh che loi tai output, giu provenance ro rang, va cho phep so sanh canonical content voi baseline.
- Bang chung: `repair_validation.document_identity_restored=true`, repaired co 24 rows/24 unique IDs, metrics tro ve baseline.

## 6. Mot loi hoac blocker da xu ly

- Trieu chung: neu corruption flow ghi nham vao baseline artifacts thi khong con so sanh duoc baseline/corrupted/repaired.
- Lenh hoac buoc tai hien: chay corruption flow sau khi baseline da duoc tao.
- Nguyen nhan goc: cac state dung chung project artifact paths, nen can phan biet ro file protected va file generated moi.
- Cach xu ly: tao danh sach protected paths, capture SHA-256 truoc corruption, sau moi checkpoint goi `_assert_hashes_unchanged`.
- Cach xac minh sau khi sua: test orchestration xac nhan hash baseline khong doi va flow ghi artifact rieng cho corrupted/repaired.
- Dieu hoc duoc: voi data pipeline, artifact isolation quan trong ngang voi metric vi metric chi co y nghia khi du lieu tham chieu khong bi drift.

## 7. Hieu biet ve luong end-to-end

1. Crossref tra raw API payload, pipeline parse thanh `PaperRecord`, cleaning normalize title/summary/date, tao `text_for_embedding`, sau do build embedding va dua vao Chroma collection.
2. Evaluation set luu cau hoi, ground truth answer va `ground_truth_doc_ids`. Retrieval hit rate do xem DOI dung co nam trong top-k khong; token F1 va judge do chat luong cau tra loi tu tai lieu retrieve duoc.
3. Quality checks bat loi schema/completeness/uniqueness/validity/consistency tren dataset. Freshness monitoring rieng ve do moi cua ngay `published` so voi threshold 180 ngay.
4. Phai dung cung test set cho baseline, corrupted va repaired de metric delta phan anh thay doi corpus/index, khong phai thay doi do kho cua cau hoi.
5. Repair thanh cong khi repaired khop baseline ve document identity/content, quality 13/13, freshness `fresh`, va agent metrics tro ve baseline.

## 8. Phan tich ket qua

| Metric/signal | Baseline | Corrupted | Repaired | Nhan xet ca nhan |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.000 | 0.500 | 1.000 | Drop latest records lam mat ground-truth IDs nen retrieval giam ro nhat |
| `mean_token_f1` | 1.000 | 0.491 | 1.000 | Summary rong/noisy va title bi cat lam cau tra loi mat factual evidence |
| `judge_accuracy` | 1.000 | 0.458 | 1.000 | Judge phat hien nhieu cau tra loi khong con dung sau corruption |
| `mean_judge_score` | 5.000 | 2.875 | 5.000 | Diem trung binh giam hon 2 diem, sau repair phuc hoi toi da |
| Quality checks | 13/13 | 11/13 | 13/13 | Duplicate ID va blank summary la hai loi quality fail |
| Freshness status | fresh | stale_or_invalid | fresh | Stale date lam co 2 rows qua nguong 180 ngay |

Chuoi nguyen nhan - bang chung:

1. Drop latest records + duplicate/summary corruption -> quality con 11/13 va freshness stale -> retrieval hit rate giam tu 1.000 xuong 0.500.
2. Rebuild tu raw snapshot -> 24 unique IDs duoc phuc hoi, quality/freshness pass -> metrics tro lai 1.000/5.000 nhu baseline.

Corruption anh huong ro nhat la drop latest records, vi no lam bien mat ground-truth documents khoi index. Khi tai lieu dung khong con trong corpus, agent khong the retrieve dung cho nhom cau hoi lien quan, nen cac metric cau tra loi cung giam theo.

## 9. Dieu hoc duoc va huong cai thien

1. Data lineage phai duoc khoa bang hash/artifact, neu khong repair co the vo tinh dua tren du lieu da drift.
2. Observability nen bat loi truoc khi nguoi dung thay cau tra loi sai; quality/freshness la early warning cho RAG.
3. Dung cung test set la dieu kien bat buoc de so sanh metric co y nghia.

Neu co them thoi gian, em se them scenario corruption cho metadata sai tac gia/category va chia metric theo `question_type`, de biet loai loi nao anh huong nhieu nhat den summary, authors, publication date va categories.

## 10. Cam ket cua thanh vien

- [x] Noi dung bao cao phan anh dung phan viec role 4.
- [x] Moi ket luan ve ket qua deu co artifact hoac metric de doi chieu.
- [x] Khong ghi da chay thanh cong cho phan khong co bang chung.
- [x] Bao cao khong chua `.env`, API key, token hoac secret.
- [x] Da dien ho ten va MSSV that truoc khi nop.

**Ho va ten:** Hoang Van Huy  
**Ngay xac nhan:** 2026-08-06
