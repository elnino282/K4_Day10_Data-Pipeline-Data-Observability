from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.utils import normalize_whitespace, write_json


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path) -> pd.DataFrame:
    """Apply deterministic, auditable corruption scenarios to clean data.

    The newest records are targeted because freshness-sensitive RAG corpora are
    especially harmed by delayed or malformed updates.  Every mutation and the
    affected document IDs are recorded for reproducibility.
    """
    required = {
        "paper_id",
        "title",
        "summary",
        "authors_joined",
        "categories_joined",
        "published",
        "age_days",
        "summary_chars",
        "text_for_embedding",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Cannot corrupt dataframe; missing columns: {sorted(missing)}")
    if len(df) < 6:
        raise ValueError("At least six rows are required for meaningful corruption scenarios.")

    corrupted = df.copy(deep=True).sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    before_rows = len(corrupted)
    scenarios: list[dict[str, object]] = []

    drop_count = max(1, min(2, len(corrupted) // 6))
    dropped_ids = corrupted.iloc[:drop_count]["paper_id"].astype(str).tolist()
    corrupted = corrupted.iloc[drop_count:].reset_index(drop=True)
    scenarios.append({"scenario": "drop_latest_records", "affected_count": len(dropped_ids), "paper_ids": dropped_ids})

    blank_indices = list(range(0, min(2, len(corrupted))))
    blank_ids = corrupted.loc[blank_indices, "paper_id"].astype(str).tolist()
    corrupted.loc[blank_indices, "summary"] = ""
    scenarios.append({"scenario": "blank_summary", "affected_count": len(blank_ids), "paper_ids": blank_ids})

    noise_start = len(blank_indices)
    noise_indices = list(range(noise_start, min(noise_start + 2, len(corrupted))))
    noise_ids = corrupted.loc[noise_indices, "paper_id"].astype(str).tolist()
    for index in noise_indices:
        corrupted.at[index, "summary"] = (
            "UNVERIFIED PIPELINE NOISE: unrelated tokens 0000 zzzz. " + str(corrupted.at[index, "summary"])
        )
    scenarios.append({"scenario": "inject_summary_noise", "affected_count": len(noise_ids), "paper_ids": noise_ids})

    truncate_indices = noise_indices
    truncate_ids = corrupted.loc[truncate_indices, "paper_id"].astype(str).tolist()
    for index in truncate_indices:
        title = str(corrupted.at[index, "title"])
        corrupted.at[index, "title"] = title[: max(8, min(18, len(title)))]
    scenarios.append({"scenario": "truncate_title", "affected_count": len(truncate_ids), "paper_ids": truncate_ids})

    stale_indices = noise_indices
    stale_ids = corrupted.loc[stale_indices, "paper_id"].astype(str).tolist()
    for index in stale_indices:
        published = pd.to_datetime(corrupted.at[index, "published"], errors="coerce")
        if not pd.isna(published):
            corrupted.at[index, "published"] = (published - pd.DateOffset(years=5)).date().isoformat()
        corrupted.at[index, "age_days"] = int(corrupted.at[index, "age_days"]) + 1826
    scenarios.append({"scenario": "stale_publication_date", "affected_count": len(stale_ids), "paper_ids": stale_ids})

    def rebuild_embedding_text(row: pd.Series) -> str:
        return normalize_whitespace(
            f"Title: {row['title']}. Abstract: {row['summary']} Authors: {row['authors_joined'] or 'Unknown'}. "
            f"Topics: {row['categories_joined'] or row.get('primary_category', 'uncategorized')}. "
            f"Published: {row['published']}."
        )

    corrupted["summary_chars"] = corrupted["summary"].fillna("").astype(str).str.len()
    corrupted["text_for_embedding"] = corrupted.apply(rebuild_embedding_text, axis=1)

    duplicate_count = min(2, len(corrupted))
    duplicates = corrupted.tail(duplicate_count).copy(deep=True)
    duplicate_ids = duplicates["paper_id"].astype(str).tolist()
    corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
    scenarios.append({"scenario": "duplicate_rows", "affected_count": len(duplicate_ids), "paper_ids": duplicate_ids})

    log = {
        "strategy": "deterministic_recent_record_corruption_v1",
        "before_rows": before_rows,
        "after_rows": len(corrupted),
        "unique_paper_ids_before": int(df["paper_id"].nunique()),
        "unique_paper_ids_after": int(corrupted["paper_id"].nunique()),
        "scenarios": scenarios,
    }
    write_json(output_log_path, log)
    return corrupted.reset_index(drop=True)
