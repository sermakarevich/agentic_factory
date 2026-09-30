from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import ContextPressure
from agentic_factory.job.coders.opencode.harness import OpencodeHarness
from agentic_factory.job.contract import Job
from agentic_factory.tokens import Tokens, Usage

FIXTURE = Path(__file__).parent / "fixtures" / "echo.jsonl"
CUT = Path(__file__).parent / "fixtures" / "cut.jsonl"  # last step_finish dropped by opencode
MESSAGES = Path(__file__).parent / "fixtures" / "messages.json"  # what session.message.list prints


def parse_all(harness: OpencodeHarness, text: str) -> list[Event]:
    return [event for line in text.splitlines() for event in harness.parse_line(line)]


def test_command_includes_model_prompt_and_session() -> None:
    job = Job(provider="opencode", model="opencode-go/muse-spark-1.3", prompt="hi", workdir="/tmp")
    argv = OpencodeHarness().command(job)
    assert argv[:3] == ["opencode", "run", "--standalone"]
    assert "--format" in argv and "json" in argv
    assert argv[argv.index("--model") + 1] == "opencode-go/muse-spark-1.3"
    assert argv[-1] == "hi"
    assert "--session" not in argv
    resumed = OpencodeHarness().command(job.model_copy(update={"session_id": "ses_1"}))
    assert resumed[resumed.index("--session") + 1] == "ses_1"


def test_session_creation_command_and_its_answer() -> None:
    harness = OpencodeHarness()
    command = harness.new_session_command("/w")
    assert command[:2] == ["opencode", "api"] and "session.create" in command
    assert harness.parse_session('{"data": {"id": "ses_1", "cost": 0}}') == "ses_1"
    with pytest.raises(ValueError, match="no session"):
        harness.parse_session('{"_tag": "InvalidRequestError", "message": "bad"}')


def test_usage_command_lists_the_sessions_messages() -> None:
    command = OpencodeHarness().usage_command("ses_1")
    assert command[:2] == ["opencode", "api"] and "session.message.list" in command
    assert command[-2:] == ["--param", "sessionID=ses_1"]


def test_usage_is_summed_over_the_assistant_messages_since_a_moment() -> None:
    """Two model turns in the fixture, at 1790778775367 and 1790778786258 ms;
    reasoning tokens are left out, as the stream leaves them out."""
    harness = OpencodeHarness()
    before_both = datetime.fromtimestamp(1790778775.0, UTC)
    between = datetime.fromtimestamp(1790778780.0, UTC)
    after_both = datetime.fromtimestamp(1790778790.0, UTC)
    text = MESSAGES.read_text()
    assert harness.parse_usage(text, between) == Usage(
        tokens=Tokens(input=3264, output=11, cache_read=9841), cost_usd=0.000354482
    )
    both = harness.parse_usage(text, before_both)
    assert both.tokens == Tokens(input=9862 + 3264, output=69 + 11, cache_read=9841)
    assert both.cost_usd == pytest.approx(0.0011444 + 0.000354482)
    assert harness.parse_usage(text, after_both) == Usage()


def test_usage_of_something_else_than_messages_is_an_error() -> None:
    with pytest.raises(ValueError, match="no messages"):
        OpencodeHarness().parse_usage('{"_tag": "NotFoundError"}', datetime.now(UTC))


def test_captured_stream_becomes_events() -> None:
    harness = OpencodeHarness()
    events = parse_all(harness, FIXTURE.read_text())
    kinds = [e.kind for e in events]
    assert kinds == [
        EventKind.SESSION,
        EventKind.AI,
        EventKind.TOOL,
        EventKind.AI,
        EventKind.FINISHED,
    ]
    session, turn1, tool, turn2, _ = events
    assert session.session_id.startswith("ses_")
    assert turn1.tool_calls[0].name == "shell"
    assert turn1.tool_calls[0].args == {"command": "echo hello"}
    assert turn1.usage is not None and turn1.usage.input == 8847
    assert tool.tool_call_id == turn1.tool_calls[0].id
    assert tool.content == "hello\n"
    assert turn2.content == "done"
    assert all(e.session_id == session.session_id for e in events)
    assert turn2.at > turn1.at


def test_finished_carries_totals() -> None:
    harness = OpencodeHarness()
    finished = parse_all(harness, FIXTURE.read_text())[-1]
    assert finished.kind == EventKind.FINISHED
    assert finished.usage is not None
    assert finished.usage.input == 8847 + 11718
    assert finished.usage.output == 49 + 86
    assert finished.cost_usd == 0.0


def test_length_reason_raises_context_pressure() -> None:
    harness = OpencodeHarness()
    with pytest.raises(ContextPressure):
        harness.parse_line(
            '{"type":"step_finish","sessionID":"s","part":{"reason":"length","tokens":{}}}'
        )


def test_lines_without_a_rule_become_unknown_events_with_the_text() -> None:
    harness = OpencodeHarness()
    assert harness.parse_line("") == [] and harness.parse_line("\n") == []
    (noise,) = harness.parse_line("plugin loaded: foo\n")
    assert noise.kind == EventKind.UNKNOWN and noise.content == "plugin loaded: foo"
    (novel,) = harness.parse_line('{"type":"reasoning","sessionID":"s","part":{}}')
    assert novel.kind == EventKind.UNKNOWN and novel.raw["type"] == "reasoning"


def test_end_of_stream_flushes_the_turn_and_finishes_when_the_last_line_was_dropped() -> None:
    harness = OpencodeHarness()
    events = parse_all(harness, CUT.read_text())
    assert EventKind.FINISHED not in [e.kind for e in events]
    tail = harness.end_of_stream()
    assert [e.kind for e in tail] == [EventKind.AI, EventKind.FINISHED]
    assert tail[0].content == "done" and tail[0].usage is None
    assert tail[1].usage is None and tail[1].cost_usd == 0.0  # the totals were on the lost line
    assert harness.end_of_stream() == []


def test_failed_tool_call_is_flagged() -> None:
    harness = OpencodeHarness()
    harness.parse_line('{"type":"step_start","sessionID":"s","part":{"type":"step-start"}}')
    harness.parse_line(
        '{"type":"tool_use","sessionID":"s","part":{"id":"c1","type":"tool","tool":"shell",'
        '"state":{"status":"error","input":{"command":"false"},"error":"exit 1"}}}'
    )
    events = harness.parse_line(
        '{"type":"step_finish","sessionID":"s","part":{"reason":"stop","tokens":{}}}'
    )
    tool = next(e for e in events if e.kind == EventKind.TOOL)
    assert tool.error and tool.content == "exit 1" and tool.name == "shell"


def test_end_of_stream_after_a_tool_calls_step_is_not_finished() -> None:
    """The stream stopped where the model was about to start another step."""
    harness = OpencodeHarness()
    lines = FIXTURE.read_text().splitlines()[:3]  # step_start, tool_use, step_finish tool-calls
    parse_all(harness, "\n".join(lines))
    assert [e.kind for e in harness.end_of_stream()] == []


def test_end_of_stream_with_a_pending_tool_call_flushes_the_turn_unfinished() -> None:
    harness = OpencodeHarness()
    parse_all(harness, "\n".join(CUT.read_text().splitlines()[:3]))  # a tool call, no step_finish
    tail = harness.end_of_stream()
    assert [e.kind for e in tail] == [EventKind.AI, EventKind.TOOL]
