import subprocess
import threading
import time
import urllib.error

import pytest

from distill.contract import SourceKind
from distill.sources import SourceError, cli, http

_YT_TRACEBACK = """\
IpBlocked:
Could not retrieve a transcript for the video https://www.youtube.com/watch?v=abc!
YouTube is blocking requests from your IP. This usually is due to one of the
following reasons:
- You have done too many requests and your IP has been blocked by YouTube
Also make sure that there are no open issues which already describe your problem!
"""


class _Done:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_ip_block_is_transient_and_names_the_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/yt")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: _Done(1, stderr=_YT_TRACEBACK))
    with pytest.raises(SourceError) as caught:
        cli.run(["yt", "transcript", "u"], what="youtube transcript")
    assert caught.value.transient is True
    assert "already describe your problem" not in str(caught.value)
    assert "blocking this machine's IP" in str(caught.value)


def test_disabled_transcript_is_transient_because_a_block_looks_the_same(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/yt")
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *a, **k: _Done(1, stderr="transcripts are disabled")
    )
    with pytest.raises(SourceError) as caught:
        cli.run(["yt", "transcript", "u"], what="youtube transcript")
    assert caught.value.transient is True
    assert "no transcript offered" in str(caught.value)


def test_gone_video_is_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/yt")
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *a, **k: _Done(1, stderr="VideoUnavailable: gone")
    )
    with pytest.raises(SourceError) as caught:
        cli.run(["yt", "transcript", "u"], what="youtube transcript")
    assert caught.value.transient is False


def test_unrecognised_failure_keeps_the_last_line_and_is_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/yt")
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *a, **k: _Done(3, stderr="first\nsomething odd")
    )
    with pytest.raises(SourceError) as caught:
        cli.run(["yt", "transcript", "u"], what="youtube transcript")
    assert caught.value.transient is False
    assert "something odd" in str(caught.value)


def test_timeout_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired(cmd="yt", timeout=1)

    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/yt")
    monkeypatch.setattr(cli.subprocess, "run", _boom)
    with pytest.raises(SourceError) as caught:
        cli.run(["yt", "transcript", "u"], what="youtube transcript")
    assert caught.value.transient is True


def test_missing_binary_is_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    with pytest.raises(SourceError) as caught:
        cli.run(["yt", "transcript", "u"], what="youtube transcript")
    assert caught.value.transient is False


@pytest.mark.parametrize(
    ("code", "transient"),
    [(429, True), (503, True), (500, True), (404, False), (403, False)],
)
def test_http_status_decides_transience(code: int, transient: bool) -> None:
    exc = urllib.error.HTTPError("http://x", code, "nope", None, None)
    assert http.transient(exc) is transient


def test_throttle_serialises_one_kind_and_spaces_calls() -> None:
    throttle = cli.Throttle()
    overlap = threading.Event()
    inside = threading.Semaphore(0)
    live = []
    guard = threading.Lock()

    def work() -> None:
        with throttle.hold(SourceKind.youtube):
            with guard:
                live.append(1)
                if len(live) > 1:
                    overlap.set()
            time.sleep(0.05)
            with guard:
                live.pop()
        inside.release()

    threads = [threading.Thread(target=work) for _ in range(3)]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    elapsed = time.monotonic() - started
    assert not overlap.is_set()
    limit = cli.throttle_limit(SourceKind.youtube)
    assert limit is not None
    assert elapsed >= 2 * limit.gap_sec


def test_throttle_lets_an_unlisted_kind_straight_through() -> None:
    throttle = cli.Throttle()
    started = time.monotonic()
    for _ in range(5):
        with throttle.hold(SourceKind.article):
            pass
    assert time.monotonic() - started < 0.5
