"""What a finished job workflow means for its bead: closed, or blocked.

A bead is closed only when its workflow completed with a result and its coder
submitted a report whose verdict is `done`. Anything else blocks it, so its dependents stay
unready until someone retries it or closes it by hand.
"""

from pydantic import BaseModel

from agentic_factory.job.outcome import JobOutcome, verdict_of
from agentic_factory.job.report.contract import JobReport, Verdict

COMPLETED = "COMPLETED"


class Ending(BaseModel):
    """Close the bead or block it, and the one line its comment says."""

    close: bool
    note: str


def ending_of_completed(outcome: JobOutcome) -> Ending:
    """A completed workflow's bead: closed on a `done` verdict, else blocked with why."""
    if outcome.result is None:
        return Ending(close=False, note=f"failed: {outcome.failure or 'no result'}")
    verdict = verdict_of(outcome)
    if outcome.report is None:
        note = f"verdict {verdict.value}: session {outcome.session_id} submitted no report"
        return Ending(close=False, note=note)
    if verdict != Verdict.DONE:
        return Ending(close=False, note=f"verdict {verdict.value}: {_first_gap(outcome.report)}")
    return Ending(close=True, note=f"session {outcome.session_id}, verdict done")


def ending_of_stopped(workflow_id: str, status: str) -> Ending:
    """A workflow that failed, timed out, was terminated or cancelled: blocked."""
    return Ending(close=False, note=f"workflow {workflow_id} ended {status}")


def _first_gap(report: JobReport) -> str:
    """The first thing not done, else the first problem, else the task."""
    return next(iter([*report.not_done, *report.problems]), report.task)
