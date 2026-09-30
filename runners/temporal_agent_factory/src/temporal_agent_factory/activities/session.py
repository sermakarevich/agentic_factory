from temporalio import activity

from agent_factory.failure import JobFailed
from agent_factory.job import session as sessions
from agent_factory.job.contract import Job
from temporal_agent_factory.failure import to_application_error


@activity.defn
async def create_session(job: Job) -> str:
    """The session the job's tries will share. Made once, before the first try,
    so every try starts the coder the same way; Temporal remembers the result."""
    try:
        return await sessions.create_session(job)
    except JobFailed as failure:
        raise to_application_error(failure) from failure
