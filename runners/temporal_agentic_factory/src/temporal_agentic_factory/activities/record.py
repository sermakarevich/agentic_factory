from temporalio import activity

from agentic_factory.job import record as records
from agentic_factory.job.outcome import JobOutcome
from temporal_agentic_factory.activities.store import store


@activity.defn
async def record_job(outcome: JobOutcome) -> None:
    """The job row, once the workflow has its outcome. What goes in it is the
    app's `record_job`; this activity only gives it the store."""
    await records.record_job(store(), outcome)
