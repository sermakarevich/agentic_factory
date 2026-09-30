from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.exceptions import ActivityError, ApplicationError

    from agentic_factory.job.contract import Job, JobResult
    from agentic_factory.job.outcome import JobOutcome
    from agentic_factory.job.report.contract import JobReport
    from temporal_agentic_factory.activities.job import execute_job
    from temporal_agentic_factory.activities.record import record_job
    from temporal_agentic_factory.activities.report import ReportRequest, build_report
    from temporal_agentic_factory.activities.session import create_session
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


def _step_retry() -> RetryPolicy:
    return RetryPolicy(maximum_attempts=settings.step_activity.max_attempts)


async def _with_session(job: Job) -> Job:
    """The job with a session id: made once before try 1, reused by retries."""
    if job.session_id:
        return job
    return job.model_copy(update={"session_id": await _created_session_id(job)})


async def _created_session_id(job: Job) -> str:
    """The create_session activity with the job policy."""
    cfg = settings.job_activity
    return await workflow.execute_activity(
        create_session,
        job,
        start_to_close_timeout=timedelta(seconds=cfg.session_timeout_sec),
        retry_policy=_job_retry(),
    )


async def _execute_job_activity(job: Job) -> JobResult:
    """One job run: the execute_job activity with a timeout past the job's own,
    a heartbeat timeout past its stall limit, and the retries from settings."""
    cfg = settings.job_activity
    return await workflow.execute_activity(
        execute_job,
        job,
        start_to_close_timeout=timedelta(seconds=job.timeout_sec + cfg.close_margin_sec),
        heartbeat_timeout=timedelta(seconds=job.stall_sec + cfg.heartbeat_margin_sec),
        retry_policy=_job_retry(),
    )


def _failure_text(error: ActivityError) -> str:
    """The cause's message when the activity failed with a typed error."""
    cause = error.cause
    if isinstance(cause, ApplicationError):
        return f"{cause.type}: {cause.message}"
    return str(error)


async def run_job_with_report(job: Job) -> JobOutcome:
    """The job, then the report over everything it stored, then the job's row
    in the store. A job without a session gets one first, so that every try
    runs in it. A permanently failed job still gets its report, then the
    outcome carries the failure instead of a result. A failed report step is
    not fatal: the outcome has none. Neither is a failed record: the outcome
    is still returned."""
    job = await _with_session(job)
    request = await _job_as_report_request(job)
    report = await _report_or_none(request)
    outcome = JobOutcome(
        session_id=job.session_id,
        result=request.result,
        failure=request.failure,
        report=report,
    )
    await _recorded(outcome)
    return outcome


async def _job_as_report_request(job: Job) -> ReportRequest:
    """The job run, as the report step wants it: its result, or the failure
    that ended it after every try."""
    try:
        return ReportRequest(session_id=job.session_id, result=await _execute_job_activity(job))
    except ActivityError as error:
        return ReportRequest(session_id=job.session_id, failure=_failure_text(error))


async def _report_or_none(request: ReportRequest) -> JobReport | None:
    """The report activity with the step policy; None when it failed for good."""
    cfg = settings.step_activity
    try:
        return await workflow.execute_activity(
            build_report,
            request,
            start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
            retry_policy=_step_retry(),
        )
    except ActivityError:
        return None


async def _recorded(outcome: JobOutcome) -> None:
    """The record_job activity with the record policy; a write that failed
    for good is logged, not raised: the outcome is worth more than its row."""
    cfg = settings.record_activity
    try:
        await workflow.execute_activity(
            record_job,
            outcome,
            start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        )
    except ActivityError:
        workflow.logger.warning("job %s ended but its row was not written", outcome.session_id)
