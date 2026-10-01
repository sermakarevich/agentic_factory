"""What a stage's jobs were to write, checked on disk: every file there,
every test folder with a test file in it."""

import re
from pathlib import Path

TEST_FILE = re.compile(r"^test_|_test\.|\.test\.|\.spec\.|^test\.")  # test_x.py, x_test.go


def missing_files(repo: Path, paths: list[str]) -> list[str]:
    """The paths, relative to the repo, that are not a file there."""
    return [path for path in paths if not (repo / path).is_file()]


def folders_without_tests(repo: Path, folders: list[str]) -> list[str]:
    """The folders, relative to the repo, holding no test file at any depth."""
    return [folder for folder in folders if not _has_test_file(repo / folder)]


def _has_test_file(folder: Path) -> bool:
    return folder.is_dir() and any(
        path.is_file() and TEST_FILE.search(path.name) for path in folder.rglob("*")
    )
