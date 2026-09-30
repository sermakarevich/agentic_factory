import asyncio

from factory_store.schema import Outcome
from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job import engine as jobs
from agentic_factory.job.continuation import continue_job
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.observe.fanout import Fanout
from agentic_factory.observe.journal import JournalObserver
from agentic_factory.observe.log import LogObserver
from temporal_agentic_factory.failure import to_application_error
from temporal_agentic_factory.heartbeat import Heartbeat, HeartbeatObserver
from temporal_agentic_factory.store import store

CANCELLED = "cancelled"


@activity.defn
async def execute_job(job: Job) -> JobResult:
    """One try of the job. Temporal retries by re-running this with the same
    `job`, session included; the heartbeat of the earlier try only says how
    big that session got, so the engine can compact it before resuming.
    The try and every event of it go to the store, so nothing is lost when
    a try fails or the runner dies."""
    info = activity.info()
    previous = Heartbeat.last(info.heartbeat_details)
    job = continue_job(job, info.attempt, previous.context_tokens if previous else 0)
    db = store()
    await db.start_try(job.session_id, info.attempt)
    journal = JournalObserver(db, job.session_id, info.attempt)
    observer = Fanout(HeartbeatObserver(), LogObserver(), journal)
    try:
        result = await jobs.run(job, observer)
    except JobFailed as failure:
        await db.finish_try(job.session_id, info.attempt, Outcome.FAILED, str(failure))
        raise to_application_error(failure) from failure
    except asyncio.CancelledError:
        await db.finish_try(job.session_id, info.attempt, Outcome.FAILED, CANCELLED)
        raise
    await db.finish_try(job.session_id, info.attempt, Outcome.DONE)
    return result
