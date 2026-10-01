from pydantic import BaseModel, Field

from agentic_factory.job.contract import JobResult
from agentic_factory.job.report.contract import JobReport


class JobOutcome(BaseModel):
    """What a job workflow returns: the engine's result (None when every try
    failed) and the report a model wrote over the whole session."""

    session_id: str
    result: JobResult | None = None
    failure: str = Field(default="", description="The last try's failure, when there is no result.")
    report: JobReport | None = Field(default=None, description="None when the report step failed.")


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
