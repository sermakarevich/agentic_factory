from datetime import UTC, datetime
from typing import Any

from factory_store.store import Totals

from agentic_factory.callbacks.journal import JournalCallback
from agentic_factory.event import Event, EventKind, ToolCall
from agentic_factory.job.callback import JobEnd
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.stats import JobStats
from agentic_factory.tokens import Tokens


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def start_try(self, session_id: str, attempt: int) -> None:
        self.calls.append(("start_try", session_id, attempt))

    async def append_event(
        self, session_id: str, attempt: int, at: datetime, kind: str, payload: dict[str, Any]
    ) -> int:
        self.calls.append(("append_event", session_id, attempt, at, kind, payload))
        return len(self.calls)

    async def finish_try(self, *args: Any) -> None:
        self.calls.append(("finish_try", *args))


def journal(store: FakeStore) -> JournalCallback:
    return JournalCallback(store, "s1", 2)  # type: ignore[arg-type]


async def test_the_try_is_opened_on_start() -> None:
    store = FakeStore()
    await journal(store).on_start(Job(prompt="p", workdir=".", session_id="s1"))
    assert store.calls == [("start_try", "s1", 2)]


async def test_every_event_is_written_with_the_given_session_and_try() -> None:
    store = FakeStore()
    recorder = journal(store)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    await recorder.on_event(Event(kind=EventKind.SESSION, at=at))  # no session id on the event
    await recorder.on_event(
        Event(
            kind=EventKind.AI,
            at=at,
            session_id="s1",
            content="hi",
            tool_calls=[ToolCall(id="c1", name="bash", args={"cmd": "ls"})],
            raw={"type": "text"},
        )
    )
    assert [(c[1], c[2], c[4]) for c in store.calls] == [("s1", 2, "session"), ("s1", 2, "ai")]
    payload = store.calls[1][5]
    assert payload["tool_calls"] == [{"id": "c1", "name": "bash", "args": {"cmd": "ls"}}]
    assert payload["raw"] == {"type": "text"} and store.calls[1][3] == at


async def test_a_done_end_closes_the_try_with_its_totals_and_result() -> None:
    store = FakeStore()
    result = JobResult(session_id="s1", tokens=Tokens(input=10, output=4), cost_usd=0.5)
    end = JobEnd(
        result=result,
        tokens=result.tokens,
        cost_usd=0.5,
        duration_sec=2.5,
        stats=JobStats(turns=3, tool_calls=2, tool_failures=1),
    )
    await journal(store).on_end(end)
    totals = Totals(
        input_tokens=10,
        output_tokens=4,
        cost_usd=0.5,
        duration_sec=2.5,
        turns=3,
        tool_calls=2,
        tool_failures=1,
    )
    assert store.calls == [
        ("finish_try", "s1", 2, "done", "", totals, result.model_dump(mode="json"))
    ]


async def test_a_failed_end_closes_the_try_with_the_failure() -> None:
    store = FakeStore()
    end = JobEnd(
        failure="Stalled: quiet", tokens=Tokens(), cost_usd=0, duration_sec=1, stats=JobStats()
    )
    await journal(store).on_end(end)
    assert store.calls == [
        ("finish_try", "s1", 2, "failed", "Stalled: quiet", Totals(duration_sec=1), {})
    ]
