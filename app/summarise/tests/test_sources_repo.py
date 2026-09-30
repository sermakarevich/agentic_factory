"""Tests for the summarise codebase track: repo detect, clone, chunk, build."""

import urllib.request
from pathlib import Path
from typing import ClassVar, Self

import pytest

from summarise import sources
from summarise.chunking import chunk_repo
from summarise.sources import SourceKind, detect, fetch


class _Done:
    """Stand-in for a finished subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_repo(root: Path) -> Path:
    """A tiny two-component repo: README, manifest, cli/ and storage/ dirs."""
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


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://github.com/acme/widgets", SourceKind.repo),
        ("https://github.com/acme/widgets/", SourceKind.repo),
        ("https://github.com/acme/widgets/tree/main/src", SourceKind.repo),
        ("https://www.github.com/acme/widgets", SourceKind.repo),
        ("https://github.com/acme/widgets/blob/main/README.md", SourceKind.article),
        ("https://github.com/acme/widgets/issues/12", SourceKind.article),
        ("https://github.com/acme", SourceKind.article),
        ("https://gist.github.com/acme/abc123", SourceKind.article),
        ("https://acme.github.io/widgets/", SourceKind.article),
        ("https://example.com/some/article", SourceKind.article),
    ],
)
def test_detect_routes_repos_and_single_documents(url: str, kind: SourceKind) -> None:
    """Repo roots and tree URLs clone; blob/gist/pages/owner URLs stay articles."""
    assert detect(url) is kind


def _fake_clone(monkeypatch: pytest.MonkeyPatch, fail: bool = False) -> None:
    """Pretend `git clone` materialises a repo (or fails like a 404)."""

    def _run(argv: list[str], **_kwargs: object) -> _Done:
        if argv[:2] == ["git", "clone"]:
            if fail:
                return _Done(1, stderr="ERROR: Repository not found.")
            _make_repo(Path(argv[-1]))
            return _Done(0)
        if "rev-parse" in argv:
            return _Done(0, stdout="deadbee\n")
        raise AssertionError(f"unexpected argv {argv}")

    monkeypatch.setattr(sources.subprocess, "run", _run)
    monkeypatch.setattr(sources.shutil, "which", lambda _name: "/usr/bin/git")


def test_fetch_repo_clones_and_reads_overview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A repo URL shallow-clones into the work dir; README+manifest seed the text."""
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
    """Private/404 clones fall back to the README-first article fetch."""
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


def test_chunk_repo_is_one_chunk_per_component(tmp_path: Path) -> None:
    """Overview first, then one chunk per top-level dir named after it."""
    repo = _make_repo(tmp_path / "repo")
    chunks = chunk_repo(repo, 12000)
    assert [chunk.title for chunk in chunks] == ["Overview", "cli", "storage"]
    assert [chunk.slug for chunk in chunks] == ["01-overview", "02-cli", "03-storage"]
    assert "widget factory" in chunks[0].text
    assert "def main():" in chunks[1].text
    assert "class Store:" in chunks[2].text


def test_readme_title_skips_boilerplate_headings() -> None:
    """A README opening on Sponsor/License still titles from the real heading."""
    text = "# CyberVerse\n\nA world.\n\n## Sponsor\n\nThanks.\n"
    assert sources._readme_title(text, "acme", "widgets") == "CyberVerse"
    boilerplate_only = "## Sponsor\n\nThanks to Compshare.\n\n## License\n\nMIT\n"
    assert sources._readme_title(boilerplate_only, "acme", "widgets") == "acme/widgets"
