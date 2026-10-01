"""A scripted `bd`: records every call, answers by subcommand, can fail one."""

import json
from pathlib import Path
from typing import Any

from temporal_agentic_factory.watchers.beads.shell import BeadsError


class FakeBd:
    """Stands in for `run_bd`: `replies` maps a subcommand to its stdout (a
    string, or a value dumped as JSON); `failing` subcommands raise."""

    def __init__(self, replies: dict[str, Any] | None = None, failing: set[str] | None = None):
        self.replies = replies or {}
        self.failing = failing or set()
        self.calls: list[tuple[list[str], Path, int]] = []

    def __call__(self, args: list[str], cwd: Path, timeout_sec: int) -> str:
        self.calls.append((args, cwd, timeout_sec))
        if args[0] in self.failing:
            raise BeadsError(f"bd {' '.join(args)} failed (rc=1): boom")
        reply = self.replies.get(args[0], "")
        return reply if isinstance(reply, str) else json.dumps(reply)


def initialised_home(tmp_path: Path) -> Path:
    """A home that holds a (fake) beads database."""
    (tmp_path / ".beads").mkdir(parents=True)
    return tmp_path
