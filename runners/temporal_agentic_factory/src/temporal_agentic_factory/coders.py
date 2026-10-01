import asyncio
import signal
from collections.abc import Mapping
from datetime import timedelta

from factory_settings.shared import shared
from factory_store.store import Store
from temporalio.client import Client
from temporalio.worker import Worker

from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.settings.model import ProviderSettings
from temporal_agentic_factory.workflows.job.coder_queue import coder_queue
from temporal_agentic_factory.workflows.job.execute import JobActivity


async def serve_coders(identity: str) -> None:
    """Poll every configured provider's coder queue until SIGTERM, as
    `identity` to the server. The process's one store is made here, given to
    every worker, and closed when the polling ends."""
    client = await connect()
    store = Store.from_url(shared.store.url)
    try:
        await run_until_terminated(coder_workers(client, store, identity, settings.providers))
    finally:
        await store.dispose()


def coder_workers(
    client: Client, store: Store, identity: str, providers: Mapping[str, ProviderSettings]
) -> list[Worker]:
    """One worker per provider on its coder queue, running only execute_job,
    at most `max_concurrent` of them at once: the provider's limit on this machine."""
    activity = JobActivity(store, identity).execute_job
    grace = timedelta(seconds=settings.coders.graceful_shutdown_sec)
    return [
        Worker(
            client,
            task_queue=coder_queue(name),
            identity=identity,
            activities=[activity],
            max_concurrent_activities=provider.max_concurrent,
            graceful_shutdown_timeout=grace,
        )
        for name, provider in providers.items()
    ]


async def run_until_terminated(workers: list[Worker]) -> None:
    """The workers run together until SIGTERM or SIGINT; then each stops
    polling and gives its running coder jobs the graceful shutdown time to
    finish. Temporal retries what was cut off."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    stopper = asyncio.create_task(shut_down_on(stop, workers))
    try:
        await asyncio.gather(*(worker.run() for worker in workers))
    finally:
        if stop.is_set():
            await stopper
        else:
            stopper.cancel()


async def shut_down_on(stop: asyncio.Event, workers: list[Worker]) -> None:
    """Once `stop` is set: every worker shut down gracefully, together."""
    await stop.wait()
    await asyncio.gather(*(worker.shutdown() for worker in workers))
