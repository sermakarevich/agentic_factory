from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.exceptions import ActivityError, ApplicationError

    from agentic_factory.job.contract import Job, JobResult
    from agentic_factory.job.outcome import JobOutcome
    from agentic_factory.job.report import JobReport
    from temporal_agentic_factory.activities.job import execute_job
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


async def _with_session(job: Job) -> Job:
    """The job with a session id: made once before try 1, reused by retries."""
    cfg = settings.job_activity
    if not job.session_id:
        session_id = await workflow.execute_activity(
            create_session,
            job,
            start_to_close_timeout=timedelta(seconds=cfg.session_timeout_sec),
            retry_policy=_job_retry(),
        )
        job = job.model_copy(update={"session_id": session_id})
    return job


async def _execute(job: Job) -> JobResult:
    """One job run: the execute_job activity with its timeouts and retries."""
    cfg = settings.job_activity
    return await workflow.execute_activity(
        execute_job,
        job,
        start_to_close_timeout=timedelta(seconds=job.timeout_sec + cfg.close_margin_sec),
        heartbeat_timeout=timedelta(seconds=job.stall_sec + cfg.heartbeat_margin_sec),
        retry_policy=_job_retry(),
    )


async def run_job(job: Job) -> JobResult:
    """The job activity with its policy: a timeout past the job's own, a
    heartbeat timeout past its stall limit, and retries from settings. A job
    without a session gets one first, so that every try runs in it. For any
    workflow that has a job in it."""
    job = await _with_session(job)
    return await _execute(job)


def _describe(error: ActivityError) -> str:
    """The cause's message when the activity failed with a typed error."""
    cause = error.cause
    if isinstance(cause, ApplicationError):
        return f"{cause.type}: {cause.message}"
    return str(error)


async def run_job_with_report(job: Job) -> JobOutcome:
    """The job, then the report over everything it stored. A permanently failed
    job still gets its report, then the outcome carries the failure instead of
    a result. A failed report step is not fatal: the outcome has none."""
    job = await _with_session(job)
    request = await _execute_for_report(job)
    report = await _report(request)
    return JobOutcome(
        session_id=job.session_id,
        result=request.result,
        failure=request.failure,
        report=report,
    )


async def _execute_for_report(job: Job) -> ReportRequest:
    """The job run, as the report step wants it: its result, or the failure
    that ended it after every try."""
    try:
        return ReportRequest(session_id=job.session_id, result=await _execute(job))
    except ActivityError as error:
        return ReportRequest(session_id=job.session_id, failure=_describe(error))


async def _report(request: ReportRequest) -> JobReport | None:
    """The report activity with the step policy; None when it failed for good."""
    cfg = settings.step_activity
    try:
        return await workflow.execute_activity(
            build_report,
            request,
            start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        )
    except ActivityError:
        return None
