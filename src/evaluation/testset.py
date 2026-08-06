from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


def build_test_set(df: pd.DataFrame, output_path: str | Path) -> list[dict[str, Any]]:
    """Build a deterministic, multi-signal evaluation set from recent papers."""
    if df.empty:
        raise ValueError("Cannot build test set from empty dataframe.")
    required = {
        "paper_id",
        "title",
        "summary",
        "authors_joined",
        "categories_joined",
        "published",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Cannot build test set; missing columns: {missing}")
    if len(df) < 4:
        raise ValueError("At least four clean documents are required to build a useful evaluation set.")

    samples: list[dict[str, Any]] = []
    # Recent rows are intentional: the corruption flow removes or damages the
    # newest documents, making user-facing impact measurable on the same set.
    selected = df.head(min(6, len(df)))
    for position, (_, row) in enumerate(selected.iterrows(), start=1):
        paper_id = str(row["paper_id"])
        title = normalize_whitespace(str(row["title"]))
        categories = normalize_whitespace(str(row.get("categories_joined", ""))) or str(row.get("primary_category", ""))
        cases = [
            (
                "summary",
                f"What is the main finding or topic of the paper '{title}'?",
                first_sentence(str(row["summary"])),
            ),
            ("authors", f"Who authored the paper '{title}'?", str(row["authors_joined"]) or "Unknown"),
            ("publication_date", f"When was the paper '{title}' published?", str(row["published"])),
            ("categories", f"What categories describe the paper '{title}'?", categories),
        ]
        for question_type, question, ground_truth in cases:
            samples.append(
                {
                    "id": f"q-{position:02d}-{question_type}",
                    "question_type": question_type,
                    "question": question,
                    "ground_truth": normalize_whitespace(ground_truth),
                    "ground_truth_doc_ids": [paper_id],
                }
            )
    write_json(Path(output_path), samples)
    return samples

