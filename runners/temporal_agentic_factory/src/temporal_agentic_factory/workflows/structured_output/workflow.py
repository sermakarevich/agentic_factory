from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel, Field
    from temporalio.exceptions import ApplicationError

    from agentic_factory.job.contract import Job
    from agentic_factory.job.outcome import JobOutcome, with_follow_up_spend
    from agentic_factory.job.structured_output.ask import AskedJob
    from agentic_factory.job.structured_output.contract import Schema
    from agentic_factory.job.structured_output.reminder import reminder_job
    from agentic_factory.settings.load import settings as app_settings
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.job.workflow import (
        record_outcome,
        run_follow_up_here,
        run_job_here_or_fail,
        with_session,
    )
    from temporal_agentic_factory.workflows.structured_output.extract import (
        StructuredOutputActivity,
        StructuredOutputRequest,
    )
    from temporal_agentic_factory.workflows.structured_output.submission import (
        SubmissionActivity,
        SubmissionRequest,
    )

EXTRACTION_STEPS = 2  # the last message, then the whole conversation when that was not enough
NOT_SUBMITTED = "the coder did not submit the structured output, and the llm fallback is off"


class StructuredOutputJob(BaseModel):
    """A job and the shape of the structured output it must state."""

    job: Job
    output_schema: Schema


class JobWithStructuredOutput(BaseModel):
    """What the workflow returns: the job's outcome and the structured output
    it stated, matching the schema it was given. A caller with a model
    validates it: `Model.model_validate(result.structured_output)`."""

    outcome: JobOutcome
    structured_output: dict[str, Any] = Field(default_factory=dict)


@workflow.defn(name="job_with_structured_output")
class JobWithStructuredOutputWorkflow:
    """One job that must submit a structured output; fails when it did not."""

    @workflow.run
    async def run(self, request: StructuredOutputJob) -> JobWithStructuredOutput:
        return await run_job_here_with_structured_output(request.job, request.output_schema)


async def run_job_here_with_structured_output(job: Job, schema: Schema) -> JobWithStructuredOutput:
    """In this workflow's own history: the session made, the schema saved
    under it and the job asked to submit with `af output submit`, the job run
    with its report, then what it submitted. A coder that submitted nothing
    is reminded in the same session; still nothing, the output is picked out
    of its text by a step when the fallback is on. A job that failed for good
    has nothing to give, and an output never stated cannot be made up:
    either raises, so the workflow stops there."""
    job = await with_session(job)
    asked = await _asked_for_submission(SubmissionRequest(job=job, output_schema=schema))
    outcome = await run_job_here_or_fail(asked.job)
    outcome, submitted = await _submitted_after_reminders(asked, outcome)
    if submitted is None:
        submitted = await _from_fallback(job, schema)
    return JobWithStructuredOutput(outcome=outcome, structured_output=submitted)


async def _submitted_after_reminders(
    asked: AskedJob, outcome: JobOutcome
) -> tuple[JobOutcome, dict[str, Any] | None]:
    """The submitted output, reminding the coder up to `submit_reminders`
    times while there is none; the outcome with the reminders' spend added."""
    submitted = await _submitted(asked.job)
    reminders = 0
    while submitted is None and reminders < settings.structured_output_workflow.submit_reminders:
        reminders += 1
        outcome = await _reminded(asked, reminders, outcome)
        submitted = await _submitted(asked.job)
    return outcome, submitted


async def _reminded(asked: AskedJob, number: int, outcome: JobOutcome) -> JobOutcome:
    """Reminder `number` run in the job's session, its spend added to the
    outcome, and the job's row written again so it counts the reminder's tries."""
    tries_per_job = settings.job_activity.max_attempts
    reminder = reminder_job(asked.job, asked.command, number, tries_per_job)
    outcome = with_follow_up_spend(outcome, await run_follow_up_here(reminder))
    await record_outcome(outcome, asked.job.name)
    return outcome


async def _from_fallback(job: Job, schema: Schema) -> dict[str, Any]:
    """The output picked out of the coder's text by the extraction step;
    `StructuredOutputNotStated` when the fallback is off."""
    if not settings.structured_output_workflow.llm_fallback:
        message = f"{job.name}: {NOT_SUBMITTED}" if job.name else NOT_SUBMITTED
        raise ApplicationError(message, type="StructuredOutputNotStated", non_retryable=True)
    request = StructuredOutputRequest(session_id=job.session_id, output_schema=schema)
    return await _extracted(request, job.name)


def _submission_options(name: str) -> dict[str, Any]:
    """The submission activities' timeout and retries, labeled with the job's name."""
    cfg = settings.submission_activity
    return {
        "start_to_close_timeout": timedelta(seconds=cfg.timeout_sec),
        "retry_policy": RetryPolicy(maximum_attempts=cfg.max_attempts),
        "summary": name,
    }


async def _asked_for_submission(request: SubmissionRequest) -> AskedJob:
    return await workflow.execute_activity_method(
        SubmissionActivity.ask_for_submission, request, **_submission_options(request.job.name)
    )


async def _submitted(job: Job) -> dict[str, Any] | None:
    return await workflow.execute_activity_method(
        SubmissionActivity.read_submitted_output, job.session_id, **_submission_options(job.name)
    )


async def _extracted(request: StructuredOutputRequest, name: str) -> dict[str, Any]:
    """The extraction activity, given as long as its steps take plus a
    margin, with the structured output activity's retry policy, labeled
    with the job's name in the UI."""
    cfg = settings.structured_output_activity
    timeout_sec = EXTRACTION_STEPS * app_settings.step.timeout_sec + cfg.close_margin_sec
    return await workflow.execute_activity_method(
        StructuredOutputActivity.extract_structured_output,
        request,
        start_to_close_timeout=timedelta(seconds=timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        summary=name,
    )
