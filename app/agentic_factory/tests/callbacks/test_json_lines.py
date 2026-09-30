import io
import json
from datetime import UTC, datetime

from agentic_factory.callbacks.json_lines import JsonLinesCallback
from agentic_factory.event import Event, EventKind
from agentic_factory.job.callback import JobEnd
from agentic_factory.job.stats import JobStats
from agentic_factory.tokens import Tokens


async def test_one_parseable_line_per_event_and_one_for_the_end() -> None:
    out = io.StringIO()
    callback = JsonLinesCallback(out)
    await callback.on_event(
        Event(kind=EventKind.AI, at=datetime.now(UTC), content="hi", raw={"secret": 1})
    )
    await callback.on_end(
        JobEnd(failure="cancelled", tokens=Tokens(), cost_usd=0, duration_sec=1, stats=JobStats())
    )
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [line.get("kind") for line in lines] == ["ai", None]
    assert "raw" not in lines[0] and "result" not in lines[1]
    assert lines[1]["failure"] == "cancelled"
