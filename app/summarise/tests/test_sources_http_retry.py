"""_http_get retries arXiv's passing 406 and transient errors, not 404."""

import io
import urllib.error
from typing import ClassVar

import pytest

from summarise import sources


class _Resp(io.BytesIO):
    headers: ClassVar[dict] = {"Content-Type": "application/pdf"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _err(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://arxiv.org/pdf/1", code, "x", {}, None)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources.time, "sleep", lambda _s: None)


def _urlopen(monkeypatch: pytest.MonkeyPatch, outcomes: list) -> list:
    seen: list = []

    def fake(request, timeout):
        seen.append(request)
        item = outcomes.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(sources.urllib.request, "urlopen", fake)
    return seen


def test_406_then_ok_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _urlopen(monkeypatch, [_err(406), _Resp(b"%PDF")])
    body, ctype = sources._http_get("https://arxiv.org/pdf/1")
    assert body == b"%PDF"
    assert ctype == "application/pdf"
    assert len(seen) == 2
    assert seen[0].get_header("Accept") == "*/*"


def test_404_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _urlopen(monkeypatch, [_err(404)])
    with pytest.raises(sources.SourceError):
        sources._http_get("https://arxiv.org/pdf/1")
    assert len(seen) == 1


def test_persistent_503_gives_up_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _urlopen(monkeypatch, [_err(503), _err(503), _err(503)])
    with pytest.raises(sources.SourceError) as info:
        sources._http_get("https://arxiv.org/pdf/1")
    assert info.value.transient
    assert len(seen) == 3


class _Short(_Resp):
    headers: ClassVar[dict] = {"Content-Type": "application/pdf", "Content-Length": "10"}


class _Full(_Resp):
    headers: ClassVar[dict] = {"Content-Type": "application/pdf", "Content-Length": "4"}


def test_truncated_body_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _urlopen(monkeypatch, [_Short(b"%PD"), _Full(b"%PDF")])
    body, _ = sources._http_get("https://arxiv.org/pdf/1")
    assert body == b"%PDF"
    assert len(seen) == 2


def test_always_truncated_fails_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    _urlopen(monkeypatch, [_Short(b"%PD"), _Short(b"%PD"), _Short(b"%PD")])
    with pytest.raises(sources.SourceError, match="truncated") as info:
        sources._http_get("https://arxiv.org/pdf/1")
    assert info.value.transient
