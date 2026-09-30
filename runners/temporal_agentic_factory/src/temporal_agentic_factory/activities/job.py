from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job import engine as jobs
from agentic_factory.job.continuation import continue_job
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.observe.fanout import Fanout
from agentic_factory.observe.log import LogObserver
from temporal_agentic_factory.failure import to_application_error
from temporal_agentic_factory.heartbeat import Heartbeat, HeartbeatObserver


@activity.defn
async def execute_job(job: Job) -> JobResult:
    """One try of the job. Temporal retries by re-running this with the same
    `job`, session included; the heartbeat of the earlier try only says how
    big that session got, so the engine can compact it before resuming."""
    info = activity.info()
    previous = Heartbeat.last(info.heartbeat_details)
    job = continue_job(job, info.attempt, previous.context_tokens if previous else 0)
    observer = Fanout(HeartbeatObserver(), LogObserver())
    try:
        return await jobs.run(job, observer)
    except JobFailed as failure:
        raise to_application_error(failure) from failure
