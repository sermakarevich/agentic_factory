from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job import session as sessions
from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from temporal_agentic_factory.activities.failure import to_application_error
from temporal_agentic_factory.activities.store import store


@activity.defn
async def create_session(job: Job) -> str:
    """The session the job's tries will share. Made once, before the first try,
    so every try starts the coder the same way; Temporal remembers the result."""
    harness = harness_for(job.provider)
    job = with_default_model(job, harness)  # the row says what the engine will run
    session_id = await _created_session_id(job, harness)
    await store().start_session(session_id, job.provider, job.model, job.workdir, job.prompt)
    return session_id


async def _created_session_id(job: Job, harness: Harness) -> str:
    """The harness's new session; its failure typed for Temporal."""
    try:
        return await sessions.create_session(job, harness)
    except JobFailed as failure:
        raise to_application_error(failure) from failure
