"""A test server running `beads_poll` on a fake tick activity.

`Calls` scripts whether the tick fails and records the activities that ran.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from temporalio import activity
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.workflow import BeadsPollWorkflow, PollConfig

CONFIG = PollConfig(tick_timeout_sec=30)


@dataclass
class Calls:
    """What the fake activities saw, in order; the tick fails when `failing`."""

    failing: bool = False
    order: list[str] = field(default_factory=list)

    def activities(self) -> list[Callable[..., object]]:
        @activity.defn(name="poll")
        async def poll() -> PollSummary:
            self.order.append("tick")
            if self.failing:
                raise ApplicationError("bd is down", non_retryable=True)
            return PollSummary(spawned=["af-1"], skipped={"af-0": "no provider"})

        return [poll]


@dataclass
class Polling:
    client: Client
    queue: str


@asynccontextmanager
async def polling(calls: Calls) -> AsyncIterator[Polling]:
    """A time-skipping server with a worker for `beads_poll` on the fake tick."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[BeadsPollWorkflow],
            activities=calls.activities(),
        ):
            yield Polling(env.client, queue)
