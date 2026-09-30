import logging

from agentic_factory.job.contract import JobResult
from agentic_factory.job.report.contract import JobReport
from agentic_factory.job.report.conversation import clip_middle
from agentic_factory.observe.silent import Silent
from agentic_factory.settings.load import settings
from agentic_factory.step import engine as steps
from agentic_factory.step.contract import Step
from agentic_factory.step.providers.client import Client

log = logging.getLogger("agentic_factory.job")


SYSTEM_PROMPT = (
    "You read the full transcript of a coding agent's run: its messages, the tools it called, "
    "their outputs, and how each try ended. Report what was asked and what was actually done, "
    "using only evidence in the transcript. A claim by the agent is not evidence; a command "
    "output or a file content is. The verdict is done only if everything asked was done "
    "and checked; partial if some; failed if nothing useful or the run broke; "
    "unknown if you cannot tell."
)


def prompt_for(conversation: str, result: JobResult | None, failure: str) -> str:
    """The step's prompt: the conversation clipped to `report.max_chars`, then
    how the job ended: the coder's own summary block when there is one, or
    the failure text when the last try failed."""
    clipped = clip_middle(conversation, settings.report.max_chars)
    return "TRANSCRIPT\n" + clipped + "\n\nENDING\n" + _ending_text(result, failure)


def _ending_text(result: JobResult | None, failure: str) -> str:
    parts: list[str] = []
    if result is not None and result.summary_text:
        parts.append("The coder's own summary:\n" + result.summary_text)
    if failure:
        parts.append("The last try failed: " + failure)
    return "\n\n".join(parts) if parts else "No summary and no failure recorded."


async def report(
    conversation: str, result: JobResult | None, failure: str, client: Client
) -> JobReport:
    """One model step over the conversation. Raises the step's `JobFailed`
    when the model could not answer; the caller decides what that means.
    `client` is the one for `settings.step.provider`, the step's provider."""
    step = _report_step(conversation, result, failure)
    outcome = (await steps.run(step, Silent(), client)).parse(JobReport)
    log.info("report by %s: %s", step.provider, outcome.verdict)
    return outcome


def _report_step(conversation: str, result: JobResult | None, failure: str) -> Step:
    return Step(
        prompt=prompt_for(conversation, result, failure),
        output_schema=JobReport.model_json_schema(),
        system_prompt=SYSTEM_PROMPT,
    )
