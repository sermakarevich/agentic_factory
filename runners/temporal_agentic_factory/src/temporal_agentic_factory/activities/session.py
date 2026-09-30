from factory_store.store import Store
from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job import session as sessions
from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from temporal_agentic_factory.activities.failure import to_application_error


class SessionActivity:
    def __init__(self, store: Store) -> None:
        self.store = store

    @activity.defn
    async def create_session(self, job: Job) -> str:
        """The session the job's tries will share. Made once, before the first
        try, so every try starts the coder the same way; Temporal remembers
        the result. What a session is and what its row says is the app's
        `start_session`; this activity only types its failure for Temporal."""
        try:
            return await sessions.start_session(self.store, job, harness_for(job.provider))
        except JobFailed as failure:
            raise to_application_error(failure) from failure
