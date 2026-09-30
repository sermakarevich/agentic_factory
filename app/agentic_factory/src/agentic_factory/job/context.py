import asyncio
from asyncio.subprocess import DEVNULL, PIPE
from datetime import UTC, datetime

from agentic_factory.event import Event, EventKind, Observer
from agentic_factory.failure import ContextPressure
from agentic_factory.job.contract import Job
from agentic_factory.job.environment import environment
from agentic_factory.job.harness import Harness
from agentic_factory.settings.load import settings


def context_of(event: Event) -> int | None:
    """The context size of a model turn: what it read, from the prompt or the cache."""
    if event.usage is None:
        return None
    return event.usage.input + event.usage.cache_read + event.usage.cache_write


async def compact(harness: Harness, job: Job, session_id: str, observer: Observer) -> None:
    """Ask the coder to compact the session. Best effort: a failure is reported
    as an event and the run goes on, since the context limit still guards it."""
    proc = await asyncio.create_subprocess_exec(
        *harness.compact_command(session_id),
        cwd=job.workdir,
        env=environment(job.workdir),
        stdin=DEVNULL,
        stdout=DEVNULL,
        stderr=PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode == 0:
        outcome = "requested"
    else:
        tail = stderr[-settings.job.failure_tail_chars :].decode(errors="replace").strip()
        outcome = f"failed: {tail}"
    await observer.on_event(
        Event(
            kind=EventKind.COMPACTION,
            at=datetime.now(UTC),
            session_id=session_id,
            content=f"compaction {outcome}",
        )
    )


class ContextWatch:
    """Watches the context of every model turn of a running coder: asks for a
    compaction once it passes `compact_at_tokens` (when the coder allows that
    during a run) and raises `ContextPressure` above the job's limit."""

    def __init__(self, job: Job, harness: Harness, observer: Observer) -> None:
        self.job = job
        self.harness = harness
        self.observer = observer
        self.session_id = job.session_id
        self.pending = False  # a compaction was asked for and the context has not dropped since

    async def on_event(self, event: Event) -> None:
        if event.kind == EventKind.SESSION:
            self.session_id = event.session_id
            return
        if event.kind != EventKind.AI or (context := context_of(event)) is None:
            return
        if context > self.job.context_limit_tokens:
            raise ContextPressure(
                f"context {context} tokens > limit {self.job.context_limit_tokens}"
            )
        if context < settings.job.compact_at_tokens:
            self.pending = False  # it shrank; the next crossing may ask again
        elif not self.pending and self.harness.compacts_while_running and self.session_id:
            self.pending = True
            await compact(self.harness, self.job, self.session_id, self.observer)
