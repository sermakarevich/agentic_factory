import json
from pathlib import Path

import pytest

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import ProviderError, RateLimited
from agentic_factory.job.claude.harness import ClaudeHarness
from agentic_factory.job.contract import Job
from agentic_factory.settings.load import settings

FIXTURE = Path(__file__).parent / "fixtures" / "tool.jsonl"


def parse_all(harness: ClaudeHarness, text: str) -> list[Event]:
    return [event for line in text.splitlines() for event in harness.parse_line(line)]


def test_command_puts_prompt_first_and_skips_permissions_without_a_tool_list() -> None:
    job = Job(provider="claude", model="sonnet", prompt="hi", workdir="/tmp")
    argv = ClaudeHarness().command(job)
    assert argv[:3] == ["claude", "-p", "hi"]
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert "--dangerously-skip-permissions" in argv and "--resume" not in argv
    scoped = ClaudeHarness().command(job.model_copy(update={"tools": ["Bash", "Read"]}))
    assert scoped[scoped.index("--allowedTools") :] == ["--allowedTools", "Bash", "Read"]
    assert "--dangerously-skip-permissions" not in scoped


def test_command_starts_or_resumes_the_session_by_what_claude_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    job = Job(provider="claude", model="sonnet", prompt="hi", workdir="/tmp", session_id="s1")
    fresh = ClaudeHarness().command(job)
    assert fresh[fresh.index("--session-id") + 1] == "s1" and "--resume" not in fresh
    (tmp_path / "projects" / "-tmp").mkdir(parents=True)
    (tmp_path / "projects" / "-tmp" / "s1.jsonl").write_text("{}\n")
    resumed = ClaudeHarness().command(job)
    assert resumed[resumed.index("--resume") + 1] == "s1" and "--session-id" not in resumed
    assert ClaudeHarness().new_session_command("/tmp") == []  # the id is ours


def test_command_passes_the_compaction_threshold_within_claude_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = Job(provider="claude", model="sonnet", prompt="hi", workdir="/tmp")
    argv = ClaudeHarness().command(job)
    assert argv[argv.index("--autocompact") + 1] == str(settings.job.compact_at_tokens)
    monkeypatch.setattr(settings.job, "compact_at_tokens", 5)
    low = ClaudeHarness().command(job)
    assert low[low.index("--autocompact") + 1] == "100000"  # claude's minimum
    compact = ClaudeHarness().compact_command("s1")
    assert compact[:3] == ["claude", "-p", "/compact"] and "s1" in compact


def test_captured_stream_becomes_events() -> None:
    events = parse_all(ClaudeHarness(), FIXTURE.read_text())
    assert [e.kind for e in events] == [
        EventKind.SESSION,
        EventKind.AI,
        EventKind.RATE_LIMIT,
        EventKind.TOOL,
        EventKind.AI,
        EventKind.FINISHED,
    ]
    session, turn1, limit, tool, turn2, finished = events
    assert session.session_id == "9867a660-e058-4a72-9ce9-978f3768efd3"
    assert all(e.session_id == session.session_id for e in events)
    assert turn1.tool_calls[0].name == "Bash"
    assert turn1.tool_calls[0].args["command"] == "echo hello > hello.txt"
    assert turn1.usage is not None and turn1.usage.cache_write == 23091
    assert limit.resets_at is not None and limit.resets_at.year >= 2026
    assert tool.name == "Bash" and tool.tool_call_id == turn1.tool_calls[0].id
    assert tool.content == "(Bash completed with no output)"
    assert turn2.content == "done" and turn2.at > turn1.at
    assert finished.usage is not None and finished.usage.output == 90
    assert finished.usage.cache_read == 23091 and finished.cost_usd == pytest.approx(0.0983942)


def test_rejected_rate_limit_raises_with_reset_time() -> None:
    info = {"status": "rejected", "resetsAt": 1790812800}
    line = json.dumps({"type": "rate_limit_event", "session_id": "s", "rate_limit_info": info})
    with pytest.raises(RateLimited) as exc:
        ClaudeHarness().parse_line(line)
    assert exc.value.resets_at.timestamp() == 1790812800


def test_error_result_raises_provider_error() -> None:
    line = json.dumps(
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "boom"}
    )
    with pytest.raises(ProviderError, match="boom"):
        ClaudeHarness().parse_line(line)


def test_failed_tool_result_is_flagged() -> None:
    line = json.dumps(
        {
            "type": "user",
            "session_id": "s",
            "timestamp": "2026-09-29T19:23:41.923Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": "boom",
                        "is_error": True,
                    }
                ],
            },
        }
    )
    (event,) = ClaudeHarness().parse_line(line)
    assert event.kind == EventKind.TOOL and event.error and event.content == "boom"
