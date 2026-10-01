import re
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from distill.settings.load import settings
from distill.settings.model import ThrottleSettings
from distill.sources.source import SourceError

CAUSES: tuple[tuple[re.Pattern[str], bool, str], ...] = (
    (
        re.compile(r"IpBlocked|RequestBlocked|blocking requests from your IP", re.IGNORECASE),
        True,
        "YouTube is blocking this machine's IP (too many requests); retry later",
    ),
    (
        re.compile(r"\b429\b|too many requests|rate.?limit", re.IGNORECASE),
        True,
        "rate limited by the server; retry later",
    ),
    (
        re.compile(r"PoTokenRequired", re.IGNORECASE),
        True,
        "YouTube asked for a proof-of-origin token; retry later",
    ),
    (
        re.compile(r"\b5\d\d\b|temporarily unavailable|service unavailable", re.IGNORECASE),
        True,
        "the server failed temporarily; retry later",
    ),
    # Measured 2026-09-22: a video whose transcript was fetched minutes
    # earlier reports "transcripts are disabled", so a block looks the same.
    (
        re.compile(r"transcripts are disabled|NoTranscriptFound|no transcript", re.IGNORECASE),
        True,
        "no transcript offered (the video has none, or YouTube is hiding them); retry later",
    ),
    (
        re.compile(r"VideoUnavailable|video unavailable|\b404\b|not found", re.IGNORECASE),
        False,
        "the source is gone (404 / unavailable)",
    ),
)


def run(argv: list[str], *, what: str, kind: str | None = None) -> str:
    """Run one CLI and return stdout; missing binary or failure is a SourceError."""
    if shutil.which(argv[0]) is None:
        raise SourceError(f"{what}: `{argv[0]}` is not installed or not on PATH")
    try:
        with _THROTTLE.hold(kind):
            done = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=settings.fetch.cli_timeout_sec,
                check=False,
            )
    except subprocess.TimeoutExpired:
        raise SourceError(f"{what}: `{' '.join(argv)}` timed out", transient=True) from None
    if done.returncode != 0:
        raise _failure(what, argv, f"{done.stderr}\n{done.stdout}", done.returncode)
    if not done.stdout.strip():
        raise SourceError(f"{what}: `{' '.join(argv)}` returned no text")
    return done.stdout


def _failure(what: str, argv: list[str], output: str, returncode: int) -> SourceError:
    """Name the cause in a CLI's output and say whether a retry could help."""
    for pattern, transient, message in CAUSES:
        if pattern.search(output):
            return SourceError(f"{what}: `{' '.join(argv)}` failed: {message}", transient=transient)
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    tail = lines[-1] if lines else f"exit {returncode}"
    return SourceError(f"{what}: `{' '.join(argv)}` failed: {tail}")


def throttle_limit(kind: str | None) -> ThrottleSettings | None:
    """Fetches of this kind allowed at once and the gap between two, else None."""
    if kind == "youtube":
        return settings.fetch.throttle.youtube
    if kind == "x":
        return settings.fetch.throttle.x
    return None


class _Gate:
    """The slots of one throttled kind and when its last fetch started."""

    def __init__(self, limit: ThrottleSettings) -> None:
        self.slots = threading.Semaphore(limit.at_once)
        self.clock = threading.Lock()
        self.last_started = 0.0
        self.gap_sec = limit.gap_sec


class Throttle:
    """Cap how many fetches of one kind run at once, and space them out."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._gates: dict[str, _Gate] = {}

    def _gate(self, kind: str) -> _Gate | None:
        limit = throttle_limit(kind)
        if limit is None:
            return None
        with self._guard:
            gate = self._gates.get(kind)
            if gate is None:
                gate = _Gate(limit)
                self._gates[kind] = gate
            return gate

    @contextmanager
    def hold(self, kind: str | None) -> Iterator[None]:
        """Wait for a slot of this kind, and for the gap since the last one."""
        gate = self._gate(kind) if kind is not None else None
        if gate is None:
            yield
            return
        with gate.slots:
            with gate.clock:
                wait = gate.last_started + gate.gap_sec - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                gate.last_started = time.monotonic()
            yield


_THROTTLE = Throttle()
