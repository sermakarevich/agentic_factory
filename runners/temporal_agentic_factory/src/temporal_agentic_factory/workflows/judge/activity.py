from temporalio import activity

from agentic_factory.callback import Callback
from agentic_factory.failure import JobFailed
from agentic_factory.step.judge import engine
from agentic_factory.step.judge.catalog import judge_for
from agentic_factory.step.judge.contract import Judgment, JudgmentResult
from temporal_agentic_factory.workflows.failure import to_application_error


@activity.defn
async def judge(judgment: Judgment) -> JudgmentResult:
    """The app's judge step with the judge client of the judgment's provider.
    One short call; its events go nowhere, as the answers are the result.
    A failure keeps its type, so a rate limit sets the next try's delay."""
    client = judge_for(judgment.provider)
    try:
        return await engine.run(judgment, Callback(), client)
    except JobFailed as failure:
        raise to_application_error(failure) from failure
