from datetime import UTC, datetime

from temporalio.testing import ActivityEnvironment

from agentic_factory.event import Event, EventKind
from agentic_factory.tokens import Tokens
from temporal_agentic_factory.activities.heartbeat import Heartbeat, HeartbeatObserver


def test_last_reads_a_plain_dict_or_nothing() -> None:
    assert Heartbeat.last_of_previous_try([]) is None
    last = Heartbeat.last_of_previous_try([{"at": None, "events": 3, "context_tokens": 7}])
    assert last is not None and last.context_tokens == 7 and last.events == 3


async def test_observer_heartbeats_every_event_with_the_count() -> None:
    sent: list[Heartbeat] = []
    env = ActivityEnvironment()
    env.on_heartbeat = lambda *details: sent.append(details[0])
    observer = HeartbeatObserver()

    async def feed() -> None:
        now = datetime.now(UTC)
        await observer.on_event(Event(kind=EventKind.SESSION, at=now, session_id="s1"))
        await observer.on_event(Event(kind=EventKind.AI, at=now, content="x"))

    await env.run(feed)
    assert [h.events for h in sent] == [1, 2] and sent[-1].at is not None


async def test_observer_keeps_the_context_size_of_the_last_turn() -> None:
    env = ActivityEnvironment()
    observer = HeartbeatObserver()
    now = datetime.now(UTC)

    async def feed() -> None:
        usage = Tokens(input=100, cache_read=50)
        await observer.on_event(Event(kind=EventKind.AI, at=now, usage=usage))
        await observer.on_event(Event(kind=EventKind.TOOL, at=now))

    await env.run(feed)
    assert observer.state.context_tokens == 150
