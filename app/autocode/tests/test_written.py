"""A stage's files checked on disk."""

from pathlib import Path

from autocode.written import folders_without_tests, missing_files


def test_a_missing_file_is_named(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "R1.md").write_text("cases")

    assert missing_files(tmp_path, ["docs/R1.md", "docs/R2.md", "docs"]) == ["docs/R2.md", "docs"]


def test_a_folder_needs_a_test_file_at_any_depth(tmp_path: Path) -> None:
    (tmp_path / "tests" / "R1" / "deep").mkdir(parents=True)
    (tmp_path / "tests" / "R1" / "deep" / "test_export.py").write_text("")
    (tmp_path / "tests" / "R2").mkdir()
    (tmp_path / "tests" / "R2" / "conftest.py").write_text("")
    (tmp_path / "tests" / "R3").mkdir()
    (tmp_path / "tests" / "R3" / "export.spec.ts").write_text("")

    found = folders_without_tests(tmp_path, ["tests/R1", "tests/R2", "tests/R3", "tests/main"])

    assert found == ["tests/R2", "tests/main"]
