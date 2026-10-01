from pathlib import Path

from distill.chunking.repo import chunk_repo


def _make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# Widgets\n\nA widget factory.\n")
    (root / "pyproject.toml").write_text('[project]\nname = "widgets"\nversion = "1.2.3"\n')
    cli = root / "cli"
    cli.mkdir(exist_ok=True)
    (cli / "main.py").write_text('def main():\n    print("hi")\n')
    storage = root / "storage"
    storage.mkdir(exist_ok=True)
    (storage / "db.py").write_text("class Store:\n    pass\n")
    return root


def test_chunk_repo_is_one_chunk_per_component(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    chunks = chunk_repo(repo, 12000)
    assert [chunk.title for chunk in chunks] == ["Overview", "cli", "storage"]
    assert [chunk.slug for chunk in chunks] == ["01-overview", "02-cli", "03-storage"]
    assert "widget factory" in chunks[0].text
    assert "def main():" in chunks[1].text
    assert "class Store:" in chunks[2].text


def test_chunk_repo_without_components_is_overview_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Solo\n\nJust a readme.\n")
    chunks = chunk_repo(repo, 12000)
    assert [chunk.title for chunk in chunks] == ["Overview"]
