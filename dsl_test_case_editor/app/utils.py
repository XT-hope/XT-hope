import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    value = name.strip().lower()
    value = _SLUG_RE.sub("-", value).strip("-")
    return value or "project"


def safe_join(base: Path, *paths: Iterable[str]) -> Path:
    candidate = base.joinpath(*paths).resolve()
    base_resolved = base.resolve()
    if base_resolved not in candidate.parents and candidate != base_resolved:
        raise ValueError("Path traversal is not allowed.")
    return candidate


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
