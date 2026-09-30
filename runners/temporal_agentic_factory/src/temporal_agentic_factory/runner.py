from collections.abc import Callable
from typing import Any

from factory_settings.shared import shared
from factory_store.store import Store
from temporalio.worker import Worker

from temporal_agentic_factory.activities.job import JobActivity
from temporal_agentic_factory.activities.outputs import OutputsActivity
from temporal_agentic_factory.activities.record import RecordActivity
from temporal_agentic_factory.activities.report import ReportActivity
from temporal_agentic_factory.activities.session import SessionActivity
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import JobWorkflow
from temporal_agentic_factory.workflows.outputs import JobWithOutputsWorkflow


async def serve(identity: str) -> None:
    """Poll the task queue until stopped, as `identity` to the server. The
    process's one store is made here, given to every activity, and closed
    when the polling ends."""
    client = await connect()
    store = Store.from_url(shared.store.url)
    try:
        worker = Worker(
            client,
            task_queue=settings.temporal.task_queue,
            identity=identity,
            workflows=[JobWorkflow, JobWithOutputsWorkflow],
            activities=_activities(store, identity),
            max_concurrent_activities=settings.runner.max_concurrent_activities,
        )
        await worker.run()
    finally:
        await store.dispose()


def _activities(store: Store, identity: str) -> list[Callable[..., Any]]:
    return [
        SessionActivity(store).create_session,
        JobActivity(store, identity).execute_job,
        ReportActivity(store).build_report,
        OutputsActivity(store).extract_outputs,
        RecordActivity(store).record_job,
    ]
