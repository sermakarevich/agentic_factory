"""The test lock: a hash per test file, and every change since the lock named."""

from pathlib import Path

from autocode.lock import hashes, lock_problems


def written_tests(tmp_path: Path) -> Path:
    folder = tmp_path / "tests" / "feat"
    (folder / "R1").mkdir(parents=True)
    (folder / "R1" / "test_a.py").write_text("def test_a(): assert False\n")
    (folder / "main").mkdir()
    (folder / "main" / "test_e2e.py").write_text("def test_e2e(): assert False\n")
    return folder


def test_the_same_tests_have_the_same_hashes(tmp_path: Path) -> None:
    folder = written_tests(tmp_path)
    locked = hashes(folder)

    assert sorted(locked) == ["R1/test_a.py", "main/test_e2e.py"]
    assert lock_problems(locked, hashes(folder)) == []


def test_a_changed_test_is_named(tmp_path: Path) -> None:
    folder = written_tests(tmp_path)
    locked = hashes(folder)
    (folder / "R1" / "test_a.py").write_text("def test_a(): assert True\n")

    assert lock_problems(locked, hashes(folder)) == ["R1/test_a.py changed"]


def test_a_deleted_test_is_named(tmp_path: Path) -> None:
    folder = written_tests(tmp_path)
    locked = hashes(folder)
    (folder / "main" / "test_e2e.py").unlink()

    assert lock_problems(locked, hashes(folder)) == ["main/test_e2e.py deleted"]


def test_an_added_test_is_named(tmp_path: Path) -> None:
    folder = written_tests(tmp_path)
    locked = hashes(folder)
    (folder / "R1" / "test_b.py").write_text("def test_b(): pass\n")

    assert lock_problems(locked, hashes(folder)) == ["R1/test_b.py added"]


def test_caches_a_test_run_writes_are_not_tests(tmp_path: Path) -> None:
    folder = written_tests(tmp_path)
    locked = hashes(folder)
    (folder / "R1" / "__pycache__").mkdir()
    (folder / "R1" / "__pycache__" / "test_a.cpython-313.pyc").write_bytes(b"\0")
    (folder / ".pytest_cache").mkdir()
    (folder / ".pytest_cache" / "README.md").write_text("cache")

    assert lock_problems(locked, hashes(folder)) == []


def test_no_folder_has_no_files(tmp_path: Path) -> None:
    assert hashes(tmp_path / "missing") == {}
