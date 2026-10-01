"""The beads side of a tick: ready beads, claims, markers, closes.

Every mutation goes through `fleet bd ...` (the centralized database), every
read tolerates rows with missing keys: `bd --json` shapes drift.
"""

import contextlib
from collections.abc import Callable
from typing import Any

from temporal_agentic_factory.beads.models import Bead, BeadState
from temporal_agentic_factory.beads.shell import BeadsError, run_fleet, run_fleet_json

MARKER_PREFIX = "[af] workflow "


class BeadsClient:
    """One tick's beads calls. `runner` is injectable so ticks test without `bd`."""

    def __init__(
        self,
        timeout_sec: int,
        runner: Callable[[list[str], int], Any] = run_fleet_json,
        raw: Callable[[list[str], int], str] = run_fleet,
    ) -> None:
        self.timeout_sec = timeout_sec
        self._run_json = runner
        self._run = raw

    def ready(self) -> list[Bead]:
        """Startable beads with routing context, in queue order."""
        rows = self._run_json(["ready"], self.timeout_sec)
        beads = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            beads.append(
                Bead(
                    id=str(row["id"]),
                    title=str(row.get("title") or ""),
                    description=str(row.get("description") or ""),
                    coder=str(row.get("coder") or ""),
                    model=str(row.get("model") or ""),
                    cwd=str(row.get("cwd") or ""),
                    isolation=str(row.get("isolation") or ""),
                )
            )
        return beads

    def in_progress(self, limit: int) -> list[BeadState]:
        """Beads currently worked on, each with its comments for marker scans."""
        rows = self._run_json(
            ["bd", "list", "--status", "in_progress", "--limit", str(limit)], self.timeout_sec
        )
        states = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            bead_id = str(row["id"])
            states.append(
                BeadState(
                    id=bead_id,
                    updated_at=str(row.get("updated_at") or row.get("updated") or ""),
                    comments=self.comments(bead_id),
                )
            )
        return states

    def comments(self, bead_id: str) -> list[str]:
        """Comment bodies on one bead, newest last; [] when unreadable."""
        try:
            rows = self._run_json(["bd", "comments", bead_id], self.timeout_sec)
        except BeadsError:
            return []
        bodies = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, str):
                bodies.append(row)
            elif isinstance(row, dict):
                for key in ("body", "text", "comment"):
                    if row.get(key):
                        bodies.append(str(row[key]))
                        break
        return bodies

    def claim(self, bead_id: str) -> None:
        """Take one bead to in_progress; raises BeadsError when it is already taken."""
        self._run(["bd", "update", bead_id, "--claim"], self.timeout_sec)

    def comment(self, bead_id: str, text: str) -> None:
        """A best-effort note; a failed comment never fails the tick."""
        with contextlib.suppress(BeadsError):
            self._run(["bd", "comment", bead_id, text], self.timeout_sec)

    def close(self, bead_id: str) -> None:
        """Close a finished bead; raises BeadsError when it fails."""
        self._run(["bd", "close", bead_id], self.timeout_sec)

    def reopen(self, bead_id: str) -> None:
        """Release an orphaned claim back to open; raises BeadsError when it fails."""
        self._run(["bd", "reopen", bead_id], self.timeout_sec)


def marker_for(comments: list[str]) -> str | None:
    """The workflow id our spawn marker names, if any comment carries one."""
    for text in reversed(comments):
        at = text.find(MARKER_PREFIX)
        if at >= 0:
            return text[at + len(MARKER_PREFIX) :].split()[0]
    return None


def marker(workflow_id: str) -> str:
    """The comment a spawn leaves so later ticks recognize their own beads."""
    return f"{MARKER_PREFIX}{workflow_id}"
