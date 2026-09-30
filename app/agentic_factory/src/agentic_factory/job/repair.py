import logging

from agentic_factory.event import Event
from agentic_factory.failure import JobFailed
from agentic_factory.job.summary import SUMMARY_KEY, JobSummary
from agentic_factory.step import engine as steps
from agentic_factory.step.client import Client
from agentic_factory.step.contract import Step

log = logging.getLogger("agentic_factory.job")

SYSTEM_PROMPT = (
    f"A coding agent was asked to end its message with a json block `{SUMMARY_KEY}`: "
    "task (one sentence), plan (list of steps), execution (list of what was done), "
    "result (one sentence), success (true or false). What it wrote is below, but it does "
    "not parse or does not match that shape. Return the summary it meant, as valid json "
    "matching the schema. Keep its wording. Do not invent facts: a field it did not give "
    "is an empty string or an empty list, and success is false unless it clearly said "
    "the job succeeded."
)


class Silent:
    """The repair step's events stay out of the job's stream: a heartbeat
    observer would read the step's tokens as the coder's context."""

    async def on_event(self, event: Event) -> None:
        return None


async def repair_summary(block: str, client: Client | None = None) -> JobSummary | None:
    """Layer 5: a block that was found but did not parse, handed to a model
    with the summary schema. None when the model could not fix it either."""
    step = Step(
        prompt=block, output_schema=JobSummary.model_json_schema(), system_prompt=SYSTEM_PROMPT
    )
    try:
        summary = (await steps.run(step, Silent(), client)).parse(JobSummary)
    except JobFailed as failure:
        log.warning("summary repair failed: %s", failure)
        return None
    log.info("summary repaired by %s", step.provider)
    return summary
