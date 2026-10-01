"""The tests there were before a feature: the repo's test folders without the
feature's own, so a check of the old tests never runs the new red ones."""

from pathlib import Path

from autocode.lock import SKIPPED_DIRS


def old_tests(repo: Path, test_dirs: list[str], feature_dir: str) -> list[str]:
    """The test paths, relative to the repo, without `feature_dir`: a folder
    inside it dropped, a folder holding it replaced by everything else it holds."""
    feature = Path(feature_dir)
    return [path for folder in test_dirs for path in _without(repo, Path(folder), feature)]


def _without(repo: Path, folder: Path, feature: Path) -> list[str]:
    if folder == feature or feature in folder.parents:
        return []  # the feature's own tests
    if folder not in feature.parents:
        return [folder.as_posix()]
    if not (repo / folder).is_dir():
        return []
    children = sorted(child.name for child in (repo / folder).iterdir() if _kept(child.name))
    return [path for name in children for path in _without(repo, folder / name, feature)]


def _kept(name: str) -> bool:
    """Not a cache a test run writes, and not hidden."""
    return name not in SKIPPED_DIRS and not name.startswith(".")
