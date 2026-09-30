import asyncio

from factory_store.schema import Outcome
from factory_store.store import Store
from temporalio import activity

from agentic_factory.event import Observer
from agentic_factory.failure import JobFailed
from agentic_factory.job import engine as jobs
from agentic_factory.job.catalog import harness_for
from agentic_factory.job.continuation import continue_job
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.repair import repair_summary
from agentic_factory.job.summary import JobSummary
from agentic_factory.observe.fanout import Fanout
from agentic_factory.observe.journal import JournalObserver
from agentic_factory.observe.log import LogObserver
from agentic_factory.settings.load import settings
from agentic_factory.step.catalog import client_for
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
    job = _continued_for_this_try(job, info)
    db = store()
    await db.start_try(job.session_id, info.attempt)
    observer = _observer_for_try(db, job.session_id, info.attempt)
    return await _run_and_record_try(job, observer, db, info.attempt)


def _observer_for_try(db: Store, session_id: str, attempt: int) -> Observer:
    """Heartbeats to Temporal, lines to the log, every event to the store."""
    return Fanout(HeartbeatObserver(), LogObserver(), JournalObserver(db, session_id, attempt))


async def _run_and_record_try(job: Job, observer: Observer, db: Store, attempt: int) -> JobResult:
    """The engine run, with how it ended written to the try's row: done,
    failed with the failure's text, or cancelled."""
    try:
        result = await jobs.run(
            job, observer, harness_for(job.provider), _repair_summary_with_step_client
        )
    except JobFailed as failure:
        await db.finish_try(job.session_id, attempt, Outcome.FAILED, str(failure))
        raise to_application_error(failure) from failure
    except asyncio.CancelledError:
        await db.finish_try(job.session_id, attempt, Outcome.FAILED, CANCELLED)
        raise
    await db.finish_try(job.session_id, attempt, Outcome.DONE)
    return result


def _continued_for_this_try(job: Job, info: activity.Info) -> Job:
    """The job as this try runs it: continued from the earlier tries, with the
    session size the last heartbeat of the previous try reported."""
    previous = Heartbeat.last_of_previous_try(info.heartbeat_details)
    return continue_job(job, info.attempt, previous.context_tokens if previous else 0)


async def _repair_summary_with_step_client(block: str) -> JobSummary | None:
    """The engine's repair: the summary step with the client for the step
    provider from settings, made only when a summary needs repairing."""
    return await repair_summary(block, client_for(settings.step.provider))
