import uuid

from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.workflow import BeadsPollWorkflow


@activity.defn(name="poll")
async def fake_poll() -> PollSummary:
    """One tick without beads: stands in for the real poll activity."""
    return PollSummary(spawned=["bd-1"], closed=["bd-0"])


async def test_poll_workflow_returns_the_tick_summary() -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[BeadsPollWorkflow],
            activities=[fake_poll],
        ):
            handle = await env.client.start_workflow(
                BeadsPollWorkflow.run,
                id=f"p-{uuid.uuid4()}",
                task_queue=queue,
            )
            summary = await handle.result()
            assert summary.spawned == ["bd-1"]
            assert summary.closed == ["bd-0"]
