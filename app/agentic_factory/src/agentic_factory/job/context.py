from asyncio.subprocess import DEVNULL
from datetime import UTC, datetime

from agentic_factory.callback import Callback
from agentic_factory.event import Event, EventKind
from agentic_factory.failure import ContextPressure
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from agentic_factory.job.process.spawn import start_process
from agentic_factory.job.process.tail import tail_of
from agentic_factory.settings.load import settings


def context_of(event: Event) -> int | None:
    """The context size of a model turn: what it read, from the prompt or the cache."""
    if event.usage is None:
        return None
    return event.usage.input + event.usage.cache_read + event.usage.cache_write


async def compact(harness: Harness, job: Job, session_id: str, callback: Callback) -> None:
    """Ask the coder to compact the session. Best effort: a failure is reported
    as an event and the run goes on, since the context limit still guards it."""
    outcome = await _compaction_outcome(harness, job, session_id)
    await callback.on_event(_compaction_event(session_id, outcome))


async def _compaction_outcome(harness: Harness, job: Job, session_id: str) -> str:
    """`requested`, or `failed:` with the tail of what the command said."""
    proc = await start_process(harness.compact_command(session_id), job.workdir, stdout=DEVNULL)
    _, stderr = await proc.communicate()
    if proc.returncode == 0:
        return "requested"
    return f"failed: {tail_of(stderr)}"


def _compaction_event(session_id: str, outcome: str) -> Event:
    return Event(
        kind=EventKind.COMPACTION,
        at=datetime.now(UTC),
        session_id=session_id,
        content=f"compaction {outcome}",
    )


class ContextWatch:
    """Watches the context of every model turn of a running coder: asks for a
    compaction once it passes `compact_at_tokens` (when the coder allows that
    during a run) and raises `ContextPressure` above the job's limit."""

    def __init__(self, job: Job, harness: Harness, callback: Callback) -> None:
        self.job = job
        self.harness = harness
        self.callback = callback
        self.session_id = job.session_id
        self.pending = False  # a compaction was asked for and the context has not dropped since

    async def on_event(self, event: Event) -> None:
        if event.kind == EventKind.SESSION:
            self.session_id = event.session_id
            return
        if event.kind != EventKind.AI or (context := context_of(event)) is None:
            return
        self._raise_above_limit(context)
        await self._compact_once_above_threshold(context)

    def _raise_above_limit(self, context: int) -> None:
        if context > self.job.context_limit_tokens:
            raise ContextPressure(
                f"context {context} tokens > limit {self.job.context_limit_tokens}"
            )

    async def _compact_once_above_threshold(self, context: int) -> None:
        """One request per crossing of `compact_at_tokens`, when the coder can
        take it during a run and the session is known."""
        if context < settings.job.compact_at_tokens:
            self.pending = False  # it shrank; the next crossing may ask again
        elif not self.pending and self.harness.compacts_while_running and self.session_id:
            self.pending = True
            await compact(self.harness, self.job, self.session_id, self.callback)
