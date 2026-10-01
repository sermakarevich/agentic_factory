"""The comments af leaves on a bead, and what later ticks read back from them.

A spawn leaves `[af] workflow <id>`, a retry leaves `[af] retry`: the latest
spawn marker after the latest retry names the workflow of the current attempt,
and every spawn marker counts one attempt.
"""

MARKER_PREFIX = "[af] workflow "
RETRY = "[af] retry"
BLOCKED_PREFIX = "[af] blocked: "
DONE_PREFIX = "[af] done: "
SKIPPED_PREFIX = "[af] skipped: "


def marker(workflow_id: str) -> str:
    """The comment a spawn leaves so later ticks recognize their own beads."""
    return f"{MARKER_PREFIX}{workflow_id}"


def marker_for(comments: list[str]) -> str | None:
    """The workflow id the current attempt's spawn marker names; None when
    nothing was spawned since the bead was made or last retried."""
    for text in reversed(comments):
        if text.startswith(RETRY):
            return None
        at = text.find(MARKER_PREFIX)
        if at >= 0:
            return text[at + len(MARKER_PREFIX) :].split()[0]
    return None


def attempt_of(comments: list[str]) -> int:
    """The number of the next spawn: one more than the spawns marked so far."""
    return 1 + sum(MARKER_PREFIX in text for text in comments)


def retried(reason: str) -> str:
    """The comment a retry leaves; it ends the previous attempt's marker."""
    return f"{RETRY}: {reason}" if reason else RETRY


def blocked(note: str) -> str:
    """The one comment on a bead whose job did not finish its work."""
    return f"{BLOCKED_PREFIX}{note}"


def done(note: str) -> str:
    """The one comment on a bead closed after its job finished."""
    return f"{DONE_PREFIX}{note}"


def skipped(reason: str) -> str:
    """The comment on a ready bead that cannot become a job, left once per reason."""
    return f"{SKIPPED_PREFIX}{reason}"
