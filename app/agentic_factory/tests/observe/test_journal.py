from datetime import UTC, datetime
from typing import Any

from agentic_factory.event import Event, EventKind, ToolCall
from agentic_factory.observe.journal import JournalObserver


class FakeStore:
    def __init__(self) -> None:
        self.rows: list[tuple[Any, ...]] = []

    async def append_event(
        self, session_id: str, attempt: int, at: datetime, kind: str, payload: dict[str, Any]
    ) -> int:
        self.rows.append((session_id, attempt, at, kind, payload))
        return len(self.rows)


async def test_every_event_is_written_with_the_given_session_and_try() -> None:
    store = FakeStore()
    journal = JournalObserver(store, "s1", 2)  # type: ignore[arg-type]
    at = datetime(2026, 1, 1, tzinfo=UTC)
    await journal.on_event(Event(kind=EventKind.SESSION, at=at))  # no session id on the event
    await journal.on_event(
        Event(
            kind=EventKind.AI,
            at=at,
            session_id="s1",
            content="hi",
            tool_calls=[ToolCall(id="c1", name="bash", args={"cmd": "ls"})],
            raw={"type": "text"},
        )
    )
    assert [(r[0], r[1], r[3]) for r in store.rows] == [("s1", 2, "session"), ("s1", 2, "ai")]
    assert store.rows[1][4]["tool_calls"] == [{"id": "c1", "name": "bash", "args": {"cmd": "ls"}}]
    assert store.rows[1][4]["raw"] == {"type": "text"} and store.rows[1][2] == at
    assert journal.written == 2
