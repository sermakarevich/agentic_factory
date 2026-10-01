from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel
    from temporalio.exceptions import (
        ActivityError,
        ApplicationError,
        CancelledError,
        TimeoutError,
    )

    from agentic_factory.job.contract import Job, JobResult
    from agentic_factory.job.outcome import JobOutcome, with_follow_up_spend
    from agentic_factory.job.report.failure import failed_report
    from agentic_factory.job.submission.ask import AskedJob
    from agentic_factory.job.submission.contract import Schema
    from agentic_factory.job.submission.reminder import reminder_job
    from agentic_factory.job.submission.submit import Submitted
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.job import search_attributes
    from temporal_agentic_factory.workflows.job.coder_queue import coder_queue
    from temporal_agentic_factory.workflows.job.execute import JobActivity, TryResult
    from temporal_agentic_factory.workflows.job.record import RecordActivity
    from temporal_agentic_factory.workflows.job.session import SessionActivity
    from temporal_agentic_factory.workflows.job.submission import (
        SubmissionActivity,
        SubmissionRequest,
    )

NOT_SUBMITTED = "the coder did not submit the structured output"


class JobRequest(BaseModel):
    """A job, and the schema of the structured output it must hand back
    besides its report, when it must hand one back."""

    job: Job
    output_schema: Schema | None = None


@workflow.defn(name="job")
class JobWorkflow:
    """One job, run to a result and the report the coder submitted with it.
    Tries of it are retries of the activity, all in one session made up
    front; this workflow never sees them."""

    @workflow.run
    async def run(self, request: JobRequest) -> JobOutcome:
        return await run_job_here(request.job, request.output_schema)


def _job_retry() -> RetryPolicy:
    cfg = settings.job_activity
    return RetryPolicy(
        initial_interval=timedelta(seconds=cfg.retry_initial_sec),
        backoff_coefficient=cfg.retry_backoff,
        maximum_interval=timedelta(seconds=cfg.retry_max_sec),
        maximum_attempts=cfg.max_attempts,
    )


async def with_session(job: Job) -> Job:
    """The job with a session id: made once before try 1, reused by retries."""
    if job.session_id:
        return job
    return job.model_copy(update={"session_id": await _created_session_id(job)})


async def _created_session_id(job: Job) -> str:
    """The create_session activity with the job policy."""
    cfg = settings.job_activity
    return await workflow.execute_activity_method(
        SessionActivity.create_session,
        job,
        start_to_close_timeout=timedelta(seconds=cfg.session_timeout_sec),
        retry_policy=_job_retry(),
        summary=job.name,
    )


async def _execute_job_activity(job: Job) -> TryResult:
    """One job run: the execute_job activity on its provider's coder queue,
    with a timeout past the job's own, a heartbeat timeout past its stall
    limit, and the retries from settings. No schedule-to-start timeout: a try
    waits in the queue as long as the provider's slots are taken."""
    cfg = settings.job_activity
    return await workflow.execute_activity_method(
        JobActivity.execute_job,
        job,
        task_queue=coder_queue(job.provider),
        start_to_close_timeout=timedelta(seconds=job.timeout_sec + cfg.close_margin_sec),
        heartbeat_timeout=timedelta(seconds=job.stall_sec + cfg.heartbeat_margin_sec),
        retry_policy=_job_retry(),
        summary=job.name,
    )


def _timeout_name(timeout: TimeoutError) -> str:
    """`heartbeat`, `start to close`, ...: which limit the try ran into."""
    return timeout.type.name.lower().replace("_", " ") if timeout.type else "unknown"


def _failure_text(error: ActivityError) -> str:
    """What ended the job after its last try, as `Kind: message`: the typed
    error the try raised, a Temporal timeout (the heartbeat stopped, or the
    try outlived its start-to-close), or a cancellation."""
    cause = error.cause
    if isinstance(cause, ApplicationError):
        return f"{cause.type}: {cause.message}"
    if isinstance(cause, TimeoutError):
        return f"Timeout: {_timeout_name(cause)}"
    if isinstance(cause, CancelledError):
        return "Cancelled: the try was cancelled"
    return f"{type(cause).__name__}: {cause}" if cause else str(error)


async def run_job_here(job: Job, output_schema: Schema | None = None) -> JobOutcome:
    """In this workflow's own history: the session made, the submission
    schema saved under it and the job asked to submit its result with `af
    output submit`, the job run, then what it submitted. A coder that
    submitted nothing is reminded in the same session; still nothing, the
    outcome has no report and its verdict is unknown. A job that failed for
    good gets a report made here from its failure, and no reminder. Then
    the job's row in the store; a failed record is not fatal. A job asked
    for a structured output raises when it failed or never submitted one:
    an output cannot be made up, so the caller stops there."""
    job = await with_session(job)
    asked = await _asked_for_submission(SubmissionRequest(job=job, output_schema=output_schema))
    outcome = await _ran(asked.job)
    if outcome.failure:
        outcome = outcome.model_copy(update={"report": failed_report(job, outcome.failure)})
    else:
        outcome = await _with_submission(asked, outcome)
    workflow.upsert_search_attributes(search_attributes.at_end(outcome))
    await record_outcome(outcome, job.name)
    if output_schema is not None:
        _raise_without_output(job, outcome)
    return outcome


def _raise_without_output(job: Job, outcome: JobOutcome) -> None:
    """The named JobFailed for a job that failed for good; the named
    StructuredOutputNotStated for one that never submitted its output."""
    done_or_raised(job, outcome)
    if outcome.output is None:
        message = _named(job, NOT_SUBMITTED)
        raise ApplicationError(message, type="StructuredOutputNotStated", non_retryable=True)


async def _ran(job: Job) -> JobOutcome:
    """The job run: its result, or the failure that ended it after every
    try. Either way the runner of the last try goes to the UI."""
    try:
        done = await _execute_job_activity(job)
    except ActivityError as error:
        workflow.upsert_search_attributes(search_attributes.after_job(error.identity))
        return JobOutcome(session_id=job.session_id, failure=_failure_text(error))
    workflow.upsert_search_attributes(search_attributes.after_job(done.runner))
    return JobOutcome(session_id=job.session_id, result=done.result)


async def _with_submission(asked: AskedJob, outcome: JobOutcome) -> JobOutcome:
    """The outcome with the report and output the coder submitted, reminding
    it up to `submit_reminders` times while it has submitted nothing; the
    reminders' spend added."""
    submitted = await _submitted(asked.job)
    reminders = 0
    while submitted is None and reminders < settings.job_workflow.submit_reminders:
        reminders += 1
        outcome = await _reminded(asked, reminders, outcome)
        submitted = await _submitted(asked.job)
    if submitted is None:
        return outcome
    return outcome.model_copy(update={"report": submitted.report, "output": submitted.output})


async def _reminded(asked: AskedJob, number: int, outcome: JobOutcome) -> JobOutcome:
    """Reminder `number` run in the job's session, its spend added to the outcome."""
    tries_per_job = settings.job_activity.max_attempts
    reminder = reminder_job(asked.job, asked.command, number, tries_per_job)
    return with_follow_up_spend(outcome, await run_follow_up_here(reminder))


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


async def _submitted(job: Job) -> Submitted | None:
    return await workflow.execute_activity_method(
        SubmissionActivity.read_submission, job.session_id, **_submission_options(job.name)
    )


async def run_job_here_or_fail(job: Job) -> JobOutcome:
    """`run_job_here` for a workflow whose next step needs what this job
    made: a job that failed for good raises, so the workflow stops there
    instead of building on nothing."""
    return done_or_raised(job, await run_job_here(job))


def done_or_raised(job: Job, outcome: JobOutcome) -> JobOutcome:
    """The outcome when the job has a result; else the named JobFailed raised."""
    if outcome.result is None:
        raise job_failed(job, outcome.failure)
    return outcome


def job_failed(job: Job, failure: str) -> ApplicationError:
    """The JobFailed error a workflow stops on, with the job's name in front."""
    return ApplicationError(_named(job, failure), type="JobFailed", non_retryable=True)


def _named(job: Job, failure: str) -> str:
    """The failure with the job's name in front, when it has one: `wiki/3: Stalled: ...`."""
    return f"{job.name}: {failure}" if job.name else failure


async def run_follow_up_here(job: Job) -> JobResult | None:
    """In this workflow's own history: a follow-up job in the session of a job
    that already ran, its tries only. No report and no row of its own: the
    caller records the job's outcome again when it wants the follow-up's
    tries counted. None when it failed for good."""
    try:
        return (await _execute_job_activity(job)).result
    except ActivityError:
        return None


async def record_outcome(outcome: JobOutcome, name: str) -> None:
    """The record_job activity with the record policy, labeled with the job's
    name in the UI; a write that failed for good is logged, not raised: the
    outcome is worth more than its row."""
    cfg = settings.record_activity
    try:
        await workflow.execute_activity_method(
            RecordActivity.record_job,
            outcome,
            start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
            summary=name,
        )
    except ActivityError:
        workflow.logger.warning("job %s ended but its row was not written", outcome.session_id)
