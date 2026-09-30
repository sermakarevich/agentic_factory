from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job import session as sessions
from agentic_factory.job.contract import Job
from temporal_agentic_factory.failure import to_application_error
from temporal_agentic_factory.store import store


@activity.defn
async def create_session(job: Job) -> str:
    """The session the job's tries will share. Made once, before the first try,
    so every try starts the coder the same way; Temporal remembers the result."""
    try:
        session_id = await sessions.create_session(job)
    except JobFailed as failure:
        raise to_application_error(failure) from failure
    await store().start_session(session_id, job.provider, job.model, job.workdir, job.prompt)
    return session_id
