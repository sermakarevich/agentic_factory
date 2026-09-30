from collections.abc import Awaitable, Callable

from agentic_factory.event import Event
from agentic_factory.job.callback import JobCallback, JobEnd
from agentic_factory.job.contract import Job


class Fanout(JobCallback):
    """One callback that forwards everything to several, in order. Every
    callback hears every call even when an earlier one raised; the first
    error is raised once all have been told."""

    def __init__(self, *callbacks: JobCallback) -> None:
        self.callbacks = callbacks

    async def on_start(self, job: Job) -> None:
        await _each(self.callbacks, lambda callback: callback.on_start(job))

    async def on_event(self, event: Event) -> None:
        await _each(self.callbacks, lambda callback: callback.on_event(event))

    async def on_end(self, end: JobEnd) -> None:
        await _each(self.callbacks, lambda callback: callback.on_end(end))


async def _each(
    callbacks: tuple[JobCallback, ...], call: Callable[[JobCallback], Awaitable[None]]
) -> None:
    """`call` on every callback; the first error raised after the last call."""
    first: Exception | None = None
    for callback in callbacks:
        try:
            await call(callback)
        except Exception as error:
            first = first or error
    if first is not None:
        raise first
