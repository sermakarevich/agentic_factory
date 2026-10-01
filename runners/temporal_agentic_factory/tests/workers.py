"""Test workers laid out as the real processes are: workflows and quick
activities on one queue (the runner), execute_job on every provider's coder
queue (`af coders`)."""

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job.coder_queue import coder_queue


@asynccontextmanager
async def running(
    client: Client,
    queue: str,
    workflows: Sequence[type],
    activities: Sequence[Callable[..., Any]],
    execute: Callable[..., Any],
) -> AsyncIterator[None]:
    """The runner's worker on `queue` and one coder worker per provider, all running."""
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(
            Worker(client, task_queue=queue, workflows=workflows, activities=activities)
        )
        for provider in settings.providers:
            await stack.enter_async_context(
                Worker(client, task_queue=coder_queue(provider), activities=[execute])
            )
        yield
