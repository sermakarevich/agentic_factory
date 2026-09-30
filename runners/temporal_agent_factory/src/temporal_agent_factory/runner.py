from temporalio.worker import Worker

from temporal_agent_factory.activities.job import execute_job
from temporal_agent_factory.activities.session import create_session
from temporal_agent_factory.activities.step import execute_step
from temporal_agent_factory.client import connect
from temporal_agent_factory.settings.load import settings
from temporal_agent_factory.workflows.job import JobWorkflow


async def serve() -> None:
    """Poll the task queue until stopped."""
    client = await connect()
    worker = Worker(
        client,
        task_queue=settings.temporal.task_queue,
        workflows=[JobWorkflow],
        activities=[create_session, execute_job, execute_step],
        max_concurrent_activities=settings.runner.max_concurrent_activities,
    )
    await worker.run()
