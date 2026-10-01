"""The old tests: the repo's test folders without the feature's own."""

from pathlib import Path

from autocode.old_tests import old_tests


def tree(repo: Path, *paths: str) -> None:
    for path in paths:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("")


def test_a_folder_beside_the_feature_stays(tmp_path: Path) -> None:
    tree(tmp_path, "tests/core/test_words.py")

    assert old_tests(tmp_path, ["tests/core"], "tests/stats") == ["tests/core"]


def test_a_folder_inside_the_feature_is_dropped(tmp_path: Path) -> None:
    tree(tmp_path, "tests/core/test_words.py", "tests/stats/R1/__pycache__/x.pyc")

    assert old_tests(tmp_path, ["tests/core", "tests/stats", "tests/stats/R1"], "tests/stats") == [
        "tests/core"
    ]


def test_a_folder_holding_the_feature_becomes_everything_else_it_holds(tmp_path: Path) -> None:
    tree(
        tmp_path,
        "tests/conftest.py",
        "tests/core/test_words.py",
        "tests/stats/R1/test_top.py",
        "tests/__pycache__/x.pyc",
        "tests/.hidden/x",
    )

    assert old_tests(tmp_path, ["tests"], "tests/stats") == ["tests/conftest.py", "tests/core"]


def test_a_folder_holding_the_feature_deeper_down_is_split_at_each_level(tmp_path: Path) -> None:
    tree(tmp_path, "tests/unit/test_a.py", "tests/features/old/test_b.py", "tests/features/stats/x")

    assert old_tests(tmp_path, ["tests"], "tests/features/stats") == [
        "tests/features/old",
        "tests/unit",
    ]


def test_a_missing_folder_holding_the_feature_gives_nothing(tmp_path: Path) -> None:
    assert old_tests(tmp_path, ["tests"], "tests/stats") == []
