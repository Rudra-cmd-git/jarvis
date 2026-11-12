"""Small, dependency-free helpers shared by the whole app."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|passwd|secret)\b\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\b[A-Z0-9]{32,}\b"),
    re.compile(r"\b(?:\d[ -]?){4}\s?(?:\d[ -]?){4}\s?(?:\d[ -]?){4}\b"),
    re.compile(r"(?i)\botp\b\s*[:=]?\s*\d{4,8}"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def truncate(text: str, limit: int = 400, suffix: str = "…") -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))] + suffix


def redact(text: str) -> str:
    """Remove anything that looks like a credential before storing or logging it."""
    if not text:
        return ""
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[redacted]", result)
    return result


def contains_secret(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def format_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def is_within(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> bool:
    """True when *path* is inside *root* (case-insensitive on Windows)."""
    try:
        target = Path(path).resolve()
        base = Path(root).resolve()
    except OSError:
        return False
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def first_existing(*paths: str | os.PathLike[str]) -> Path | None:
    for candidate in paths:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def safe_slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text or "").strip("-._")
    return (slug or "item")[:max_len]