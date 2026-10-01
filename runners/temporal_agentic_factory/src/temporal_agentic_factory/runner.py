from collections.abc import Callable
from typing import Any

from factory_settings.shared import shared
from factory_store.store import Store
from temporalio.worker import Worker

from temporal_agentic_factory.cleaner.clean import clean_history
from temporal_agentic_factory.cleaner.workflow import CleanerWorkflow
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.tick import BeadsPollActivity
from temporal_agentic_factory.watchers.beads.workflow import BeadsPollWorkflow
from temporal_agentic_factory.workflows.distill.activities import fetch_source, verify_entry
from temporal_agentic_factory.workflows.distill.workflow import DistillWorkflow
from temporal_agentic_factory.workflows.job.record import RecordActivity
from temporal_agentic_factory.workflows.job.report import ReportActivity
from temporal_agentic_factory.workflows.job.session import SessionActivity
from temporal_agentic_factory.workflows.job.workflow import JobWorkflow
from temporal_agentic_factory.workflows.judge.activity import judge
from temporal_agentic_factory.workflows.research.activities import locate_target, read_candidates
from temporal_agentic_factory.workflows.research.workflow import ResearchWorkflow
from temporal_agentic_factory.workflows.structured_output.extract import StructuredOutputActivity
from temporal_agentic_factory.workflows.structured_output.submission import SubmissionActivity
from temporal_agentic_factory.workflows.structured_output.workflow import (
    JobWithStructuredOutputWorkflow,
)
from temporal_agentic_factory.workflows.tutorial.activities import locate_tutorial
from temporal_agentic_factory.workflows.tutorial.workflow import TutorialWorkflow


async def serve(identity: str) -> None:
    """Poll the main task queue until stopped, as `identity` to the server:
    every workflow and the quick activities. Coder runs wait on their
    provider's queue for `af coders`. The process's one store is made here,
    given to every activity, and closed when the polling ends."""
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
                TutorialWorkflow,
                BeadsPollWorkflow,
                CleanerWorkflow,
            ],
            activities=_activities(store),
            max_concurrent_activities=settings.runner.max_concurrent_activities,
        )
        await worker.run()
    finally:
        await store.dispose()


def _activities(store: Store) -> list[Callable[..., Any]]:
    return [
        SessionActivity(store).create_session,
        ReportActivity(store).build_report,
        SubmissionActivity(store).ask_for_submission,
        SubmissionActivity(store).read_submitted_output,
        StructuredOutputActivity(store).extract_structured_output,
        RecordActivity(store).record_job,
        fetch_source,
        verify_entry,
        judge,
        locate_target,
        read_candidates,
        locate_tutorial,
        BeadsPollActivity().poll,
        clean_history,
    ]
