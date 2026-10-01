from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.exceptions import (
        ActivityError,
        ApplicationError,
        CancelledError,
        TimeoutError,
    )

    from agentic_factory.job.contract import Job
    from agentic_factory.job.outcome import JobOutcome
    from agentic_factory.job.report.contract import JobReport
    from agentic_factory.settings.load import settings as app_settings
    from temporal_agentic_factory import search_attributes
    from temporal_agentic_factory.activities.job import JobActivity, TryResult
    from temporal_agentic_factory.activities.record import RecordActivity
    from temporal_agentic_factory.activities.report import ReportActivity, ReportRequest
    from temporal_agentic_factory.activities.session import SessionActivity
    from temporal_agentic_factory.settings.load import settings


@workflow.defn(name="job")
class JobWorkflow:
    """One job, run to a result. Tries of it are retries of the activity, all
    in one session made up front; this workflow never sees them."""

    @workflow.run
    async def run(self, job: Job) -> JobOutcome:
        return await run_job_with_report(job)


def _job_retry() -> RetryPolicy:
    cfg = settings.job_activity
    return RetryPolicy(
        initial_interval=timedelta(seconds=cfg.retry_initial_sec),
        backoff_coefficient=cfg.retry_backoff,
        maximum_interval=timedelta(seconds=cfg.retry_max_sec),
        maximum_attempts=cfg.max_attempts,
    )


def _report_retry() -> RetryPolicy:
    return RetryPolicy(maximum_attempts=settings.report_activity.max_attempts)


async def _with_session(job: Job) -> Job:
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
    """One job run: the execute_job activity with a timeout past the job's own,
    a heartbeat timeout past its stall limit, and the retries from settings."""
    cfg = settings.job_activity
    return await workflow.execute_activity_method(
        JobActivity.execute_job,
        job,
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


async def run_job_with_report(job: Job) -> JobOutcome:
    """The job, then the report over everything it stored, then the job's row
    in the store. A job without a session gets one first, so that every try
    runs in it. A permanently failed job still gets its report, then the
    outcome carries the failure instead of a result. A failed report step is
    not fatal: the outcome has none. Neither is a failed record: the outcome
    is still returned."""
    job = await _with_session(job)
    request = await _job_as_report_request(job)
    report = await _report_or_none(request, job.name)
    outcome = JobOutcome(
        session_id=job.session_id,
        result=request.result,
        failure=request.failure,
        report=report,
    )
    workflow.upsert_search_attributes(search_attributes.at_end(outcome))
    await _recorded(outcome, job.name)
    return outcome


async def run_job_or_fail(job: Job) -> JobOutcome:
    """`run_job_with_report` for a workflow whose next step needs what this
    job made: a job that failed for good raises, so the workflow stops
    there instead of building on nothing."""
    outcome = await run_job_with_report(job)
    if outcome.result is None:
        raise ApplicationError(_named(job, outcome.failure), type="JobFailed", non_retryable=True)
    return outcome


def _named(job: Job, failure: str) -> str:
    """The failure with the job's name in front, when it has one: `wiki/3: Stalled: ...`."""
    return f"{job.name}: {failure}" if job.name else failure


async def _job_as_report_request(job: Job) -> ReportRequest:
    """The job run, as the report step wants it: its result, or the failure
    that ended it after every try. Either way the runner of the last try goes
    to the UI."""
    try:
        done = await _execute_job_activity(job)
    except ActivityError as error:
        workflow.upsert_search_attributes(search_attributes.after_job(error.identity))
        return ReportRequest(session_id=job.session_id, failure=_failure_text(error))
    workflow.upsert_search_attributes(search_attributes.after_job(done.runner))
    return ReportRequest(session_id=job.session_id, result=done.result)


async def _report_or_none(request: ReportRequest, name: str) -> JobReport | None:
    """The report activity, given as long as the app gives its step plus a
    margin, with the report policy; None when it failed for good. Labeled
    with the job's name in the UI."""
    timeout_sec = app_settings.step.timeout_sec + settings.report_activity.close_margin_sec
    try:
        return await workflow.execute_activity_method(
            ReportActivity.build_report,
            request,
            start_to_close_timeout=timedelta(seconds=timeout_sec),
            retry_policy=_report_retry(),
            summary=name,
        )
    except ActivityError:
        return None


async def _recorded(outcome: JobOutcome, name: str) -> None:
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
