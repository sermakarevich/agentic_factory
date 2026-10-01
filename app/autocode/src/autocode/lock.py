"""The test lock: once the tests are red, no coder may change them."""

import hashlib
from pathlib import Path

SKIPPED_DIRS = frozenset({"__pycache__", ".pytest_cache"})  # caches a test run writes
SKIPPED_SUFFIXES = frozenset({".pyc"})  # compiled files a test run writes


def hashes(folder: Path) -> dict[str, str]:
    """The sha256 of every file under `folder`, by its path relative to it;
    caches a test run leaves behind are not tests. No folder, no files."""
    if not folder.is_dir():
        return {}
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and _is_test_file(path.relative_to(folder))
    }


def lock_problems(locked: dict[str, str], now: dict[str, str]) -> list[str]:
    """Every locked file changed or deleted, and every file added, since the lock."""
    return [
        *(f"{path} changed" for path in locked if path in now and now[path] != locked[path]),
        *(f"{path} deleted" for path in locked if path not in now),
        *(f"{path} added" for path in now if path not in locked),
    ]


def _is_test_file(relative: Path) -> bool:
    return relative.suffix not in SKIPPED_SUFFIXES and not SKIPPED_DIRS & set(relative.parts)
