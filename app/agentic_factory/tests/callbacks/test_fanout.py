from datetime import UTC, datetime

import pytest

from agentic_factory.callback import Callback
from agentic_factory.callbacks.fanout import Fanout
from agentic_factory.event import Event, EventKind
from agentic_factory.job.callback import JobCallback, JobEnd
from agentic_factory.job.contract import Job
from agentic_factory.job.stats import JobStats
from agentic_factory.tokens import Tokens


class Recorder(JobCallback):
    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self.log = log

    async def on_start(self, job: Job) -> None:
        self.log.append(f"{self.name} start")

    async def on_event(self, event: Event) -> None:
        self.log.append(f"{self.name} {event.kind.value}")

    async def on_end(self, end: JobEnd) -> None:
        self.log.append(f"{self.name} end")


async def test_everything_reaches_every_callback_in_order() -> None:
    log: list[str] = []
    fanout = Fanout(Recorder("a", log), Recorder("b", log))
    await fanout.on_start(Job(prompt="p", workdir="."))
    await fanout.on_event(Event(kind=EventKind.AI, at=datetime.now(UTC)))
    await fanout.on_end(JobEnd(tokens=Tokens(), cost_usd=0, duration_sec=0, stats=JobStats()))
    assert log == ["a start", "b start", "a ai", "b ai", "a end", "b end"]


async def test_the_base_callbacks_ignore_everything() -> None:
    await Callback().on_event(Event(kind=EventKind.AI, at=datetime.now(UTC)))
    callback = JobCallback()
    await callback.on_start(Job(prompt="p", workdir="."))
    await callback.on_event(Event(kind=EventKind.AI, at=datetime.now(UTC)))
    await callback.on_end(JobEnd(tokens=Tokens(), cost_usd=0, duration_sec=0, stats=JobStats()))


class Broken(JobCallback):
    async def on_event(self, event: Event) -> None:
        raise RuntimeError("journal down")


async def test_a_raising_callback_does_not_silence_the_others() -> None:
    log: list[str] = []
    fanout = Fanout(Broken(), Recorder("b", log))
    with pytest.raises(RuntimeError, match="journal down"):
        await fanout.on_event(Event(kind=EventKind.AI, at=datetime.now(UTC)))
    assert log == ["b ai"]
