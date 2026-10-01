import asyncio
import os
import signal
from datetime import timedelta

from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from temporal_agentic_factory.coders import coder_workers, run_until_terminated
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.settings.model import ProviderSettings
from temporal_agentic_factory.workflows.job.coder_queue import coder_queue
from tests.fakes import FakeStore


async def test_one_worker_per_provider_on_its_queue_with_its_limit() -> None:
    providers = {
        "claude": ProviderSettings(max_concurrent=1),
        "opencode": ProviderSettings(max_concurrent=5),
    }
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        workers = coder_workers(env.client, FakeStore(), "host:1:abc", providers)  # type: ignore[arg-type]
        configs = [worker.config() for worker in workers]
    assert [(c["task_queue"], c["max_concurrent_activities"]) for c in configs] == [
        (coder_queue("claude"), 1),
        (coder_queue("opencode"), 5),
    ]
    for config in configs:
        assert [getattr(fn, "__name__", "") for fn in config["activities"]] == ["execute_job"]
        assert not config["workflows"]
        assert config["identity"] == "host:1:abc"
        assert config["graceful_shutdown_timeout"] == timedelta(
            seconds=settings.coders.graceful_shutdown_sec
        )


class FakeWorker:
    """Runs until shut down; records that it was."""

    def __init__(self) -> None:
        self.stopped = asyncio.Event()

    async def run(self) -> None:
        await self.stopped.wait()

    async def shutdown(self) -> None:
        self.stopped.set()


async def test_sigterm_shuts_every_worker_down_gracefully() -> None:
    workers = [FakeWorker(), FakeWorker()]
    asyncio.get_running_loop().call_later(0.05, os.kill, os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_until_terminated(workers), timeout=5)  # type: ignore[arg-type]
    assert all(worker.stopped.is_set() for worker in workers)
