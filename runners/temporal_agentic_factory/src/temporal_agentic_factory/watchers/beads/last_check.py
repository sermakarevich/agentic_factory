"""The last tick as the watcher remembers it: its query answer and its one-line attribute."""

from datetime import datetime

from pydantic import BaseModel

from temporal_agentic_factory.watchers.beads.models import PollSummary

FAILED_LINE = "tick failed"


class LastCheck(BaseModel):
    """One tick: when it ended, how many beads it moved, or why it failed."""

    at: datetime
    spawned: int = 0
    closed: int = 0
    blocked: int = 0
    released: int = 0
    skipped: int = 0
    errors: int = 0
    error: str = ""

    def line(self) -> str:
        """The short text of the `LastCheck` attribute; the time is left out, so
        it only changes when what the ticks do changes."""
        if self.error:
            return FAILED_LINE
        return (
            f"spawned {self.spawned} closed {self.closed} blocked {self.blocked}"
            f" released {self.released}"
            f" skipped {self.skipped} errors {self.errors}"
        )


def check_of(at: datetime, summary: PollSummary) -> LastCheck:
    """A finished tick's counts."""
    return LastCheck(
        at=at,
        spawned=len(summary.spawned),
        closed=len(summary.closed),
        blocked=len(summary.blocked),
        released=len(summary.reopened),
        skipped=len(summary.skipped),
        errors=len(summary.errors),
    )


def failed_check(at: datetime, error: str) -> LastCheck:
    """A tick that failed after its retries, with the failure's text."""
    return LastCheck(at=at, error=error)
