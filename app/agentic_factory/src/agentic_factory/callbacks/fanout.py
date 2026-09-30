from agentic_factory.callback import Callback, JobEnd
from agentic_factory.event import Event
from agentic_factory.job.contract import Job


class Fanout(Callback):
    """One callback that forwards everything to several, in order."""

    def __init__(self, *callbacks: Callback) -> None:
        self.callbacks = callbacks

    async def on_start(self, job: Job) -> None:
        for callback in self.callbacks:
            await callback.on_start(job)

    async def on_event(self, event: Event) -> None:
        for callback in self.callbacks:
            await callback.on_event(event)

    async def on_end(self, end: JobEnd) -> None:
        for callback in self.callbacks:
            await callback.on_end(end)
