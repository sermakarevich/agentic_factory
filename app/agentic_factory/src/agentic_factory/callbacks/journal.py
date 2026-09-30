from factory_store.schema import Outcome
from factory_store.store import Store, Totals

from agentic_factory.event import Event
from agentic_factory.job.callback import JobCallback, JobEnd
from agentic_factory.job.contract import Job


class JournalCallback(JobCallback):
    """The try's recorder: opens its row when the run starts, writes every
    event as it happens, closes the row with how the run ended and what it
    added up to. The session and try are given, not read from the events:
    the first events of a run carry no session id yet."""

    def __init__(self, store: Store, session_id: str, attempt: int) -> None:
        self.store = store
        self.session_id = session_id
        self.attempt = attempt

    async def on_start(self, job: Job) -> None:
        await self.store.start_try(self.session_id, self.attempt)

    async def on_event(self, event: Event) -> None:
        await self.store.append_event(
            self.session_id, self.attempt, event.at, event.kind, event.model_dump(mode="json")
        )

    async def on_end(self, end: JobEnd) -> None:
        await self.store.finish_try(
            self.session_id,
            self.attempt,
            Outcome.DONE if end.done else Outcome.FAILED,
            end.failure,
            totals_of(end),
            end.result.model_dump(mode="json") if end.result else {},
        )


def totals_of(end: JobEnd) -> Totals:
    """The end of a run as the store's flat totals."""
    return Totals(
        input_tokens=end.tokens.input,
        output_tokens=end.tokens.output,
        cache_read_tokens=end.tokens.cache_read,
        cache_write_tokens=end.tokens.cache_write,
        cost_usd=end.cost_usd,
        duration_sec=end.duration_sec,
        turns=end.stats.turns,
        tool_calls=end.stats.tool_calls,
        tool_failures=end.stats.tool_failures,
    )
