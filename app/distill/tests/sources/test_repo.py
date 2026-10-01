import urllib.request
from pathlib import Path
from typing import ClassVar, Self

import pytest

from distill.contract import SourceKind
from distill.sources import detect, fetch
from distill.sources import repo as repo_mod
from distill.sources.github import readme_title


class _Done:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


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


def _fake_clone(monkeypatch: pytest.MonkeyPatch, fail: bool = False) -> None:
    def _run(argv: list[str], **_kwargs: object) -> _Done:
        if argv[:2] == ["git", "clone"]:
            if fail:
                return _Done(1, stderr="ERROR: Repository not found.")
            _make_repo(Path(argv[-1]))
            return _Done(0)
        if "rev-parse" in argv:
            return _Done(0, stdout="deadbee\n")
        raise AssertionError(f"unexpected argv {argv}")

    monkeypatch.setattr(repo_mod.subprocess, "run", _run)
    monkeypatch.setattr(repo_mod.shutil, "which", lambda _name: "/usr/bin/git")


def test_fetch_repo_clones_and_reads_overview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_clone(monkeypatch)
    work = tmp_path / "work"
    src = fetch("https://github.com/acme/widgets", work)
    assert src.kind is SourceKind.repo
    assert src.title == "acme/widgets"
    assert src.tool == "git-clone"
    assert (work / "repo" / "cli" / "main.py").is_file()
    assert "widget factory" in src.text
    assert "deadbee" in src.text


def test_fetch_repo_clone_failure_falls_back_to_readme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_clone(monkeypatch, fail=True)

    page = (
        "<html><head><title>acme/nope</title></head><body>"
        "<p>" + ("placeholder " * 10) + "</p>"
        "</body></html>"
    ).encode()

    class _Response:
        headers: ClassVar[dict] = {"Content-Type": "text/html"}

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self, _size: int = -1) -> bytes:
            return page

    def _open(request: object, timeout: float | None = None) -> _Response:
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", _open)
    src = fetch("https://github.com/acme/nope", tmp_path / "work")
    assert src.kind is SourceKind.article
    assert src.title == "acme/nope"


def test_detect_routes_tree_urls_to_the_clone() -> None:
    assert detect.detect("https://github.com/acme/widgets/tree/main/src") is SourceKind.repo


def test_readme_title_skips_boilerplate_headings() -> None:
    text = "# CyberVerse\n\nA world.\n\n## Sponsor\n\nThanks.\n"
    assert readme_title(text, "acme", "widgets") == "CyberVerse"
    boilerplate_only = "## Sponsor\n\nThanks to Compshare.\n\n## License\n\nMIT\n"
    assert readme_title(boilerplate_only, "acme", "widgets") == "acme/widgets"
