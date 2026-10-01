from collections.abc import Callable
from typing import Any

from factory_settings.shared import shared
from factory_store.store import Store
from temporalio.worker import Worker

from temporal_agentic_factory.client import connect
from temporal_agentic_factory.distill.activities import fetch_source, verify_entry
from temporal_agentic_factory.distill.workflow import DistillWorkflow
from temporal_agentic_factory.job.execute import JobActivity
from temporal_agentic_factory.job.record import RecordActivity
from temporal_agentic_factory.job.report import ReportActivity
from temporal_agentic_factory.job.session import SessionActivity
from temporal_agentic_factory.job.workflow import JobWorkflow
from temporal_agentic_factory.judge.activity import judge
from temporal_agentic_factory.research.activities import locate_target, read_candidates
from temporal_agentic_factory.research.workflow import ResearchWorkflow
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.structured_output.extract import StructuredOutputActivity
from temporal_agentic_factory.structured_output.workflow import JobWithStructuredOutputWorkflow


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
            workflows=[
                JobWorkflow,
                JobWithStructuredOutputWorkflow,
                DistillWorkflow,
                ResearchWorkflow,
            ],
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
        StructuredOutputActivity(store).extract_structured_output,
        RecordActivity(store).record_job,
        fetch_source,
        verify_entry,
        judge,
        locate_target,
        read_candidates,
    ]
