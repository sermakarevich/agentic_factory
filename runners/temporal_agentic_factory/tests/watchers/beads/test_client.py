from typing import Any

from temporal_agentic_factory.watchers.beads.client import (
    MARKER_PREFIX,
    BeadsClient,
    marker,
    marker_for,
)
from temporal_agentic_factory.watchers.beads.shell import BeadsError


def _client(rows: Any, raw: str = "") -> BeadsClient:
    return BeadsClient(timeout_sec=1, runner=lambda args, sec: rows, raw=lambda args, sec: raw)


def test_ready_parses_rows_and_skips_bad_ones() -> None:
    client = _client(
        [
            {
                "id": "bd-1",
                "title": "T",
                "description": "D",
                "coder": "opencode",
                "model": "m",
                "cwd": "/tmp",
                "isolation": "worktree",
            },
            {"no_id": True},
            "junk",
        ]
    )
    beads = client.ready()
    assert len(beads) == 1
    assert beads[0].id == "bd-1"
    assert beads[0].isolation == "worktree"


def test_marker_round_trip() -> None:
    assert marker_for(["noise", marker("bead-bd-1")]) == "bead-bd-1"
    assert marker_for(["nothing here"]) is None
    assert MARKER_PREFIX in marker("bead-bd-1")


def test_comment_failures_never_fail() -> None:
    def failing(args: list[str], sec: int) -> str:
        raise BeadsError("rc=1")

    BeadsClient(timeout_sec=1, raw=failing).comment("bd-1", "hi")
