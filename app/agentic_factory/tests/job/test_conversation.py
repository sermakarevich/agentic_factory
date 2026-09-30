from datetime import UTC, datetime

from factory_store.store import StoredEvent

from agentic_factory.event import Event, EventKind, ToolCall
from agentic_factory.job.conversation import clip_middle, render
from agentic_factory.tokens import Tokens

AT = datetime(2026, 1, 1, tzinfo=UTC)


def _row(id: int, attempt: int, event: Event) -> StoredEvent:
    return StoredEvent(
        id=id,
        session_id="s",
        attempt=attempt,
        at=AT,
        kind=event.kind.value,
        payload=event.model_dump(mode="json"),
    )


def test_clip_middle_keeps_head_and_tail() -> None:
    clipped = clip_middle("a" * 50 + "b" * 50, 20)
    assert len(clipped) <= 20
    assert clipped.startswith("a")
    assert clipped.endswith("b")
    assert "[...]" in clipped
    assert clip_middle("short", 20) == "short"


def test_render_marks_tries_and_clips_tool_output() -> None:
    ai = Event(
        kind=EventKind.AI,
        at=AT,
        session_id="s",
        content="plan",
        tool_calls=[ToolCall(id="c", name="bash", args={"cmd": "ls"})],
    )
    tool = Event(kind=EventKind.TOOL, at=AT, session_id="s", name="bash", content="x" * 5000)
    finished = Event(
        kind=EventKind.FINISHED,
        at=AT,
        session_id="s",
        usage=Tokens(input=10, output=5),
        cost_usd=0.5,
    )
    text = render([_row(1, 1, ai), _row(2, 1, tool), _row(3, 2, finished)])
    assert text.startswith("===== try 1 =====")
    assert text.count("===== try 2 =====") == 1
    assert '-> bash({"cmd": "ls"})' in text
    tool_line = next(line for line in text.splitlines() if line.startswith("tool bash:"))
    assert len(tool_line) < 2100
    assert "[...]" in tool_line
    assert text.splitlines()[-1] == "finished: in=10 out=5, cost $0.5000"


def test_render_empty_is_empty() -> None:
    assert render([]) == ""
