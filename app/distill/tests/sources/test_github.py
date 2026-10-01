import urllib.error
import urllib.request
from pathlib import Path
from typing import Self

import pytest

from distill.chunking.text import chunk_text
from distill.sources import SourceError, fetch

_URL = "https://github.com/octo/Hello-World"
_RAW = "https://raw.githubusercontent.com/"

_README_MD = (
    "# Hello-World\n\n"
    + ("Welcome to the project. It does wonderful things. " * 30)
    + "\n\n## Installation\n\n"
    + ("Install it like this with one simple command. " * 32)
    + "\n\n## Usage\n\n"
    + ("Use it like this every day and enjoy the results. " * 32)
)


def _sectioned_page(readme_inner: str) -> bytes:
    return (
        "<html><head><title>octo/Hello-World: My cool project</title>\n"
        '<meta name="description" content="My cool project tagline">\n'
        "</head><body>\n"
        '<a href="#start">Skip to content</a>\n'
        "<div>You signed in with another tab or window. Reload to refresh.</div>\n"
        "<nav><a>Pull requests</a><a>Issues</a></nav>\n"
        "<div>Star 12.3k Fork 456</div>\n"
        "<section><h2>Latest commit</h2><div>abc1234 fix things 2 days ago</div></section>\n"
        '<div id="readme"><article class="markdown-body">\n'
        f"{readme_inner}\n"
        "</article></div>\n"
        "<footer><div>2026 GitHub, Inc.</div></footer>\n"
        "</body></html>"
    ).encode()


_README_INNER = (
    "<h1>Hello-World</h1>\n<p>"
    + ("Welcome to the project. " * 60)
    + "</p>\n<h2>Installation</h2>\n<p>"
    + ("Install it like this. " * 60)
    + "</p>\n<h2>Usage</h2>\n<p>"
    + ("Use it like this. " * 60)
    + "</p>"
)

_READMELESS_HTML = (
    "<html><head><title>octo/Empty-Repo</title>\n"
    '<meta name="description" content="An empty little repo">\n'
    "</head><body>\n"
    '<a href="#start">Skip to content</a>\n'
    "<div>You signed in with another tab or window. Reload to refresh.</div>\n"
    "<nav><a>Pull requests</a><a>Issues</a></nav>\n"
    "<article><h2>Latest commit</h2><p>" + ("commit talk " * 120) + "</p></article>\n"
    "<footer><div>2026 GitHub, Inc.</div></footer>\n"
    "</body></html>"
).encode()


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html") -> None:
        self._body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self, _size: int = -1) -> bytes:
        return self._body


def _install(
    monkeypatch: pytest.MonkeyPatch, *, page: bytes, raws: dict[str, str | None]
) -> list[str]:
    calls: list[str] = []

    def _fake(request: object, timeout: float | None = None) -> _FakeResponse:
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        calls.append(url)
        if url.startswith(_RAW):
            text = raws.get(url.split("/")[5])
            if text is None:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return _FakeResponse(text.encode(), "text/plain")
        return _FakeResponse(page)

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    return calls


def test_fetch_github_prefers_raw_readme(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install(
        monkeypatch,
        page=_sectioned_page(_README_INNER),
        raws={"HEAD": _README_MD, "main": None, "master": None},
    )
    src = fetch(_URL, tmp_path / "work")
    assert src.tool == "raw-github"
    assert src.title == "Hello-World"
    lowered = src.text.lower()
    assert "skip to content" not in lowered
    assert "signed in with another tab" not in lowered
    assert "latest commit" not in lowered
    chunks = chunk_text(src.text, 2000)
    assert [chunk.title for chunk in chunks] == ["Hello-World", "Installation", "Usage"]


def test_fetch_github_raw_tries_refs_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _install(
        monkeypatch,
        page=_sectioned_page(_README_INNER),
        raws={"HEAD": None, "main": _README_MD, "master": _README_MD},
    )
    src = fetch(_URL, tmp_path / "work")
    assert src.tool == "raw-github"
    assert "Hello-World" in src.text
    raw_calls = [url for url in calls if url.startswith(_RAW)]
    assert [url.split("/")[5] for url in raw_calls] == ["HEAD", "main"]


def test_fetch_github_falls_back_to_readme_element(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, page=_sectioned_page(_README_INNER), raws={"HEAD": None, "main": None})
    src = fetch(_URL, tmp_path / "work")
    assert src.tool == "urllib"
    lowered = src.text.lower()
    assert "skip to content" not in lowered
    assert "signed in with another tab" not in lowered
    assert "latest commit" not in lowered
    chunks = chunk_text(src.text, 2000)
    assert len(chunks) == 3
    assert [chunk.title for chunk in chunks] == ["Hello-World", "Installation", "Usage"]


def test_fetch_github_readmelss_repo_yields_repo_named_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, page=_READMELESS_HTML, raws={"HEAD": None, "main": None})
    src = fetch("https://github.com/octo/Empty-Repo", tmp_path / "work")
    assert src.title == "octo/Empty-Repo"
    assert "latest commit" not in src.text.lower()
    chunks = chunk_text(src.text, 2000)
    assert len(chunks) == 1
    assert chunks[0].title == "octo/Empty-Repo"
    assert chunks[0].slug == "01-octo-empty-repo"


def test_fetch_github_transient_raw_failure_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _limited(request: object, timeout: float | None = None) -> _FakeResponse:
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _limited)
    with pytest.raises(SourceError) as caught:
        fetch(_URL, tmp_path / "work")
    assert caught.value.transient is True
