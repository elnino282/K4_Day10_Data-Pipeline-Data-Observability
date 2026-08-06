from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


class ArtifactValidationError(RuntimeError):
    """Raised when a pipeline artifact is missing, empty, or malformed."""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_file_artifact(path: Path, label: str) -> Path:
    if not path.is_file():
        raise ArtifactValidationError(f"Missing {label} artifact: {path}")
    if path.stat().st_size == 0:
        raise ArtifactValidationError(f"Empty {label} artifact: {path}")
    return path


def require_json_artifact(path: Path, label: str, expected_type: type | None = None) -> Any:
    require_file_artifact(path, label)
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"Invalid JSON in {label} artifact: {path}") from exc
    if expected_type is not None and not isinstance(payload, expected_type):
        raise ArtifactValidationError(
            f"Invalid {label} artifact type: expected {expected_type.__name__}, "
            f"got {type(payload).__name__}."
        )
    return payload


def file_sha256(path: Path) -> str:
    require_file_artifact(path, "hash input")
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(df, path: Path) -> None:
    ensure_parent(path)
    df.to_csv(path, index=False)


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def now_utc() -> datetime:
    return datetime.now(UTC)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "item"


def compact_join(items: Iterable[str], sep: str = ", ") -> str:
    return sep.join(item for item in items if item)


def first_sentence(text: str) -> str:
    chunks = re.split(r"(?<=[.!?])\s+", normalize_whitespace(text))
    return chunks[0] if chunks else normalize_whitespace(text)
