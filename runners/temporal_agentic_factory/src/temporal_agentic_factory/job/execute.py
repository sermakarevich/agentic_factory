from factory_store.store import Store
from pydantic import BaseModel, Field
from temporalio import activity

from agentic_factory.callbacks.fanout import Fanout
from agentic_factory.callbacks.journal import JournalCallback
from agentic_factory.callbacks.log import LogCallback
from agentic_factory.failure import JobFailed
from agentic_factory.job import engine as jobs
from agentic_factory.job.callback import JobCallback
from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.continuation import continue_job
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.summary.contract import JobSummary
from agentic_factory.job.summary.repair import repair_summary
from agentic_factory.settings.load import settings
from agentic_factory.step.providers.catalog import client_for
from temporal_agentic_factory.failure import to_application_error
from temporal_agentic_factory.heartbeat import Heartbeat, HeartbeatCallback


class TryResult(BaseModel):
    """What a try that ended with a result gives the workflow: the result and
    the runner that produced it, for the UI's `Runner` column. A failed try
    names its runner in the `ActivityError` instead."""

    result: JobResult
    runner: str = Field(description="The runner's Temporal identity: host:pid:sha.")


class JobActivity:
    def __init__(self, store: Store, runner: str) -> None:
        self.store = store
        self.runner = runner

    @activity.defn
    async def execute_job(self, job: Job) -> TryResult:
        """One try of the job. Temporal retries by re-running this with the
        same `job`, session included; the heartbeat of the earlier try only
        says how big that session got, so the engine can compact it before
        resuming. The try's row and every event of it are the journal
        callback's; this activity only wires the callbacks and maps a failure
        for Temporal."""
        info = activity.info()
        job = _continued_for_this_try(job, info)
        callback = self._callback_for_try(job.session_id, info.attempt)
        try:
            result = await jobs.run(
                job, callback, harness_for(job.provider), _repair_summary_with_step_client
            )
        except JobFailed as failure:
            raise to_application_error(failure) from failure
        return TryResult(result=result, runner=self.runner)

    def _callback_for_try(self, session_id: str, attempt: int) -> JobCallback:
        """Heartbeats to Temporal, lines to the log, the try and its events to the store."""
        journal = JournalCallback(self.store, session_id, attempt)
        return Fanout(HeartbeatCallback(), LogCallback(), journal)


def _continued_for_this_try(job: Job, info: activity.Info) -> Job:
    """The job as this try runs it: continued from the earlier tries, with the
    session size the last heartbeat of the previous try reported."""
    previous = Heartbeat.last_of_previous_try(info.heartbeat_details)
    return continue_job(job, info.attempt, previous.context_tokens if previous else 0)


async def _repair_summary_with_step_client(block: str) -> JobSummary | None:
    """The engine's repair: the summary step with the client for the step
    provider from settings, made only when a summary needs repairing."""
    return await repair_summary(block, client_for(settings.step.provider))
