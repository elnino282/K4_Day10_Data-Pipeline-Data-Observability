from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, safe_slug, write_json


REQUIRED_QUESTION_TYPES = ("summary", "authors", "date")
OPTIONAL_QUESTION_TYPES = ("categories",)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return normalize_whitespace(str(value))


def _strip_quote(value: str) -> str:
    return value.replace("'", "").strip()


def _sample_id(question_type: str, paper_id: str) -> str:
    return f"q-{question_type}-{safe_slug(paper_id)}"


def _append_sample(
    samples: list[dict[str, Any]],
    *,
    question_type: str,
    paper_id: str,
    question: str,
    ground_truth: str,
) -> None:
    if not ground_truth:
        return
    samples.append(
        {
            "id": _sample_id(question_type, paper_id),
            "question_type": question_type,
            "question": question,
            "ground_truth": ground_truth,
            "ground_truth_doc_ids": [paper_id],
        }
    )


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a fixed evaluation set from the cleaned dataframe."""
    if df.empty:
        raise ValueError("Cannot build a test set from an empty dataframe.")

    required_columns = {
        "paper_id",
        "title",
        "summary",
        "authors_joined",
        "categories_joined",
        "published",
    }
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {', '.join(missing_columns)}")

    working = df.copy()
    for column in required_columns:
        working[column] = working[column].map(_clean_text)

    valid_rows = working[
        (working["paper_id"] != "")
        & (working["title"] != "")
        & (working["summary"].str.len() >= 80)
        & (working["authors_joined"] != "")
        & (working["published"] != "")
    ].drop_duplicates(subset=["paper_id"])

    if len(valid_rows) < 3:
        raise ValueError("Need at least three valid cleaned papers to build a useful test set.")

    samples: list[dict[str, Any]] = []
    per_type_limit = 4

    for _, row in valid_rows.head(8).iterrows():
        paper_id = row["paper_id"]
        title = row["title"]
        quoted_title = _strip_quote(title)

        if sum(item["question_type"] == "summary" for item in samples) < per_type_limit:
            _append_sample(
                samples,
                question_type="summary",
                paper_id=paper_id,
                question=f"What is the main summary of '{quoted_title}'?",
                ground_truth=first_sentence(row["summary"]),
            )
        if sum(item["question_type"] == "authors" for item in samples) < per_type_limit:
            _append_sample(
                samples,
                question_type="authors",
                paper_id=paper_id,
                question=f"Who authored '{quoted_title}'?",
                ground_truth=row["authors_joined"],
            )
        if sum(item["question_type"] == "date" for item in samples) < per_type_limit:
            _append_sample(
                samples,
                question_type="date",
                paper_id=paper_id,
                question=f"When was '{quoted_title}' published?",
                ground_truth=row["published"],
            )
        if (
            sum(item["question_type"] == "categories" for item in samples) < per_type_limit
            and row["categories_joined"]
        ):
            _append_sample(
                samples,
                question_type="categories",
                paper_id=paper_id,
                question=f"What categories are listed for '{quoted_title}'?",
                ground_truth=row["categories_joined"],
            )

    if not samples:
        raise ValueError("No valid evaluation samples could be created.")

    ids = [item["id"] for item in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("Generated test set contains duplicate ids.")

    present_types = {item["question_type"] for item in samples}
    missing_types = sorted(set(REQUIRED_QUESTION_TYPES) - present_types)
    if missing_types:
        raise ValueError(
            "Clean dataframe cannot support all required question types; "
            f"missing ground truth for: {', '.join(missing_types)}"
        )

    write_json(Path(output_path), samples)
    return samples
