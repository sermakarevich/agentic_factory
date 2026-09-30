from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from agentic_factory.job.contract import Job, JobResult
    from temporal_agentic_factory.activities.job import execute_job
    from temporal_agentic_factory.activities.session import create_session
    from temporal_agentic_factory.settings.load import settings


@workflow.defn(name="job")
class JobWorkflow:
    """One job, run to a result. Tries of it are retries of the activity, all
    in one session made up front; this workflow never sees them."""

    @workflow.run
    async def run(self, job: Job) -> JobResult:
        return await run_job(job)


async def run_job(job: Job) -> JobResult:
    """The job activity with its policy: a timeout past the job's own, a
    heartbeat timeout past its stall limit, and retries from settings. A job
    without a session gets one first, so that every try runs in it. For any
    workflow that has a job in it."""
    cfg = settings.job_activity
    retry = RetryPolicy(
        initial_interval=timedelta(seconds=cfg.retry_initial_sec),
        backoff_coefficient=cfg.retry_backoff,
        maximum_interval=timedelta(seconds=cfg.retry_max_sec),
        maximum_attempts=cfg.max_attempts,
    )
    if not job.session_id:
        session_id = await workflow.execute_activity(
            create_session,
            job,
            start_to_close_timeout=timedelta(seconds=cfg.session_timeout_sec),
            retry_policy=retry,
        )
        job = job.model_copy(update={"session_id": session_id})
    return await workflow.execute_activity(
        execute_job,
        job,
        start_to_close_timeout=timedelta(seconds=job.timeout_sec + cfg.close_margin_sec),
        heartbeat_timeout=timedelta(seconds=job.stall_sec + cfg.heartbeat_margin_sec),
        retry_policy=retry,
    )
