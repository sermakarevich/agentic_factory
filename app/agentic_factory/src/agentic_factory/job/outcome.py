from typing import Any

from pydantic import BaseModel, Field

from agentic_factory.job.contract import JobResult
from agentic_factory.job.report.contract import JobReport, Verdict


class JobOutcome(BaseModel):
    """What a job workflow returns: the engine's result (None when every try
    failed), the coder's report and, for a job asked for one, its output."""

    session_id: str
    result: JobResult | None = None
    failure: str = Field(default="", description="The last try's failure, when there is no result.")
    report: JobReport | None = Field(
        default=None,
        description="What the coder submitted, or the workflow's own when the engine failed. "
        "None when the coder submitted nothing.",
    )
    output: dict[str, Any] | None = Field(
        default=None, description="The submitted output, when the job was asked for one."
    )


def verdict_of(outcome: JobOutcome) -> Verdict:
    """The report's verdict; `unknown` when there is no report."""
    return outcome.report.verdict if outcome.report else Verdict.UNKNOWN


def with_follow_up_spend(outcome: JobOutcome, follow_up: JobResult | None) -> JobOutcome:
    """The outcome with what a follow-up job in its session spent added to
    its result: tokens, cost and time. A follow-up with no result, or an
    outcome without one, leaves it as it is."""
    if outcome.result is None or follow_up is None:
        return outcome
    mine = outcome.result
    added = mine.model_copy(
        update={
            "tokens": mine.tokens + follow_up.tokens,
            "cost_usd": mine.cost_usd + follow_up.cost_usd,
            "duration_sec": mine.duration_sec + follow_up.duration_sec,
            "usage_known": mine.usage_known and follow_up.usage_known,
        }
    )
    return outcome.model_copy(update={"result": added})
