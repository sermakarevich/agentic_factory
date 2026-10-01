"""A test server running the watcher on fake tick and trim activities.

`Ticks` scripts what each tick does; time only moves when a test calls
`env.sleep`, so a test decides when the next tick comes.
"""

import asyncio
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
from temporal_agentic_factory.watchers.beads.workflow import BeadsWatcherWorkflow, WatcherConfig
from temporal_agentic_factory.workflows.job import search_attributes

INTERVAL_SEC = 10


@dataclass
class Ticks:
    """What the fake activities saw: ticks run, trims run, and which ticks fail."""

    failing: set[int] = field(default_factory=set)
    ticks: int = 0
    trims: int = 0

    def activities(self) -> list[Callable[..., object]]:
        @activity.defn(name="poll")
        async def poll() -> PollSummary:
            self.ticks += 1
            if self.ticks in self.failing:
                raise ApplicationError("bd is down", non_retryable=True)
            return PollSummary(spawned=[f"af-{self.ticks}"], skipped={"af-0": "no provider"})

        @activity.defn(name="trim_watcher_runs")
        async def trim() -> int:
            self.trims += 1
            return 0

        return [poll, trim]


def config(checks_per_run: int = 100) -> WatcherConfig:
    """Loop knobs for tests: a 10 s interval, `checks_per_run` ticks per run."""
    return WatcherConfig(
        interval_sec=INTERVAL_SEC,
        tick_timeout_sec=30,
        trim_timeout_sec=30,
        checks_per_run=checks_per_run,
    )


@dataclass
class Watching:
    env: WorkflowEnvironment
    client: Client
    queue: str


@asynccontextmanager
async def watching(ticks: Ticks) -> AsyncIterator[Watching]:
    """A time-skipping server with the attributes registered and a worker for the watcher."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        names = [key.name for key in search_attributes.KEYS]
        await search_attributes.add(env.client, "default", names)
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[BeadsWatcherWorkflow],
            activities=ticks.activities(),
        ):
            yield Watching(env, env.client, queue)


async def until(watch: Watching, done: Callable[[], bool], step_sec: int = 0) -> None:
    """Wait (moving time by `step_sec` each round) until `done()`; fail after 200 rounds."""
    for _ in range(200):
        if done():
            return
        if step_sec:
            await watch.env.sleep(step_sec)
        await asyncio.sleep(0.05)
    raise AssertionError("condition never held")
