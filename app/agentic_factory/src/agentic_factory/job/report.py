import logging
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agentic_factory.job.contract import JobResult
from agentic_factory.job.conversation import clip_middle
from agentic_factory.job.repair import Silent
from agentic_factory.settings.load import settings
from agentic_factory.step import engine as steps
from agentic_factory.step.client import Client
from agentic_factory.step.contract import Step

log = logging.getLogger("agentic_factory.job")


class Verdict(StrEnum):
    DONE = "done"  # everything asked for was done and checked
    PARTIAL = "partial"  # some of it
    FAILED = "failed"  # nothing useful, or the run broke
    UNKNOWN = "unknown"  # the conversation does not say


class JobReport(BaseModel):
    """What a model concluded from the whole conversation. Independent of the
    coder's own summary, which is a claim. `extra="forbid"`, no defaults: the
    schema goes to the model in strict mode."""

    model_config = ConfigDict(extra="forbid")
    task: str = Field(description="One sentence: what was asked.")
    done: list[str] = Field(
        description="What was done, with the evidence seen (files, commands, test results)."
    )
    not_done: list[str] = Field(description="What was asked but not done, or not verified.")
    problems: list[str] = Field(description="Errors, retries, rate limits, wrong turns.")
    verdict: Verdict


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
    parts: list[str] = []
    if result is not None and result.summary_text:
        parts.append("The coder's own summary:\n" + result.summary_text)
    if failure:
        parts.append("The last try failed: " + failure)
    ending = "\n\n".join(parts) if parts else "No summary and no failure recorded."
    return "TRANSCRIPT\n" + clipped + "\n\nENDING\n" + ending


async def report(
    conversation: str, result: JobResult | None, failure: str, client: Client
) -> JobReport:
    """One model step over the conversation. Raises the step's `JobFailed`
    when the model could not answer; the caller decides what that means.
    `client` is the one for `settings.step.provider`, the step's provider."""
    step = Step(
        prompt=prompt_for(conversation, result, failure),
        output_schema=JobReport.model_json_schema(),
        system_prompt=SYSTEM_PROMPT,
    )
    outcome = (await steps.run(step, Silent(), client)).parse(JobReport)
    log.info("report by %s: %s", step.provider, outcome.verdict)
    return outcome
