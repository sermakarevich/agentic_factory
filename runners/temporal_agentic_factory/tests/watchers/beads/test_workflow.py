import uuid

import pytest
from temporalio.client import WorkflowFailureError

from temporal_agentic_factory.watchers.beads.workflow import BeadsPollWorkflow
from tests.watchers.beads.fake_poll import CONFIG, Calls, polling


async def test_a_run_ticks_then_trims_and_returns_the_ticks_summary() -> None:
    calls = Calls()
    async with polling(calls) as poll:
        summary = await poll.client.execute_workflow(
            BeadsPollWorkflow.run, CONFIG, id=f"p-{uuid.uuid4()}", task_queue=poll.queue
        )
    assert calls.order == ["tick", "trim"]
    assert summary.spawned == ["af-1"]
    assert summary.skipped == {"af-0": "no provider"}


async def test_a_failed_tick_still_trims_then_fails_the_run() -> None:
    calls = Calls(failing=True)
    async with polling(calls) as poll:
        with pytest.raises(WorkflowFailureError) as failed:
            await poll.client.execute_workflow(
                BeadsPollWorkflow.run, CONFIG, id=f"p-{uuid.uuid4()}", task_queue=poll.queue
            )
    assert calls.order == ["tick", "trim"]
    assert "bd is down" in str(failed.value.cause.cause)
