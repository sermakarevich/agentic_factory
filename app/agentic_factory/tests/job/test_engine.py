import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import CoderCrashed, ContextPressure, Stalled
from agentic_factory.job.callback import JobCallback, JobEnd
from agentic_factory.job.coders.opencode.harness import OpencodeHarness
from agentic_factory.job.contract import Job
from agentic_factory.job.engine import run
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Tokens

FIXTURE = Path(__file__).parent / "coders" / "opencode" / "fixtures" / "echo.jsonl"
MESSAGES = FIXTURE.parent / "messages.json"


class Recorder(JobCallback):
    def __init__(self) -> None:
        self.started: list[Job] = []
        self.events: list[Event] = []
        self.ends: list[JobEnd] = []

    async def on_start(self, job: Job) -> None:
        self.started.append(job)

    async def on_event(self, event: Event) -> None:
        self.events.append(event)

    async def on_end(self, end: JobEnd) -> None:
        self.ends.append(end)


class ScriptedCoder(OpencodeHarness):
    """The real opencode parser, but the process is a shell script."""

    def __init__(self, script: str) -> None:
        super().__init__()
        self.script = script

    def new_session_command(self, workdir: str) -> list[str]:
        return []  # a uuid, not a process; `command` ignores the job anyway

    def command(self, job: Job) -> list[str]:
        return ["sh", "-c", self.script]


class CoderWithRecord(ScriptedCoder):
    """A scripted coder whose usage record is another shell script."""

    def __init__(self, script: str, record_script: str) -> None:
        super().__init__(script)
        self.record_script = record_script

    def usage_command(self, session_id: str) -> list[str]:
        return ["sh", "-c", self.record_script]


def messages_made_now(path: Path) -> None:
    """The messages fixture with its turns re-dated to just after now, so
    that they count as this try's."""
    data = json.loads(MESSAGES.read_text())
    for message in data["data"]:
        message["time"]["created"] = int(datetime.now(UTC).timestamp() * 1000) + 1000
    path.write_text(json.dumps(data))


def job(**overrides: object) -> Job:
    base = {"provider": "opencode", "model": "m", "prompt": "p", "workdir": str(FIXTURE.parent)}
    return Job.model_validate({**base, **overrides})


async def test_a_job_without_a_session_runs_in_a_new_one() -> None:
    class SessionCoder(ScriptedCoder):
        def new_session_command(self, workdir: str) -> list[str]:
            return ["sh", "-c", 'echo \'{"data": {"id": "ses_made"}}\'']

        def command(self, job: Job) -> list[str]:
            return ["sh", "-c", f"echo {job.session_id} > sess.txt; {self.script}"]

    workdir = FIXTURE.parent
    await run(job(), Recorder(), harness=SessionCoder(f"cat {FIXTURE}"))
    assert (workdir / "sess.txt").read_text().strip() == "ses_made"
    (workdir / "sess.txt").unlink()


async def test_replayed_stream_gives_result_and_events() -> None:
    observer = Recorder()
    result = await run(job(), observer, harness=ScriptedCoder(f"cat {FIXTURE}"))
    assert result.session_id.startswith("ses_")
    assert result.tokens.input == 8847 + 11718 and result.usage_known
    assert result.duration_sec > 0
    assert [e.kind for e in observer.events][-1] == EventKind.FINISHED
    assert result.stats.model_dump() == {"turns": 2, "tool_calls": 1, "tool_failures": 0}
    assert observer.ends  # on_end once, and on_start once, with the session made
    (started,) = observer.started
    assert started.session_id and started.model
    (end,) = observer.ends
    assert end.done and end.result == result and end.failure == ""
    assert end.tokens == result.tokens and end.stats == result.stats


class PromptEchoCoder(ScriptedCoder):
    """The model's text is the prompt it was given: the test sees what the engine sent."""

    def command(self, job: Job) -> list[str]:
        return ["python3", "-c", self.script, job.prompt]


ECHO_PROMPT = """
import json, sys
line = lambda t, part: print(json.dumps({"type": t, "sessionID": "ses_1", "part": part}))
line("step_start", {"type": "step-start"})
line("text", {"type": "text", "text": sys.argv[1]})
line("step_finish", {"type": "step-finish", "reason": "stop", "tokens": {}})
"""


async def test_the_prompt_goes_to_the_coder_as_it_is() -> None:
    observer = Recorder()
    result = await run(job(prompt="do it"), observer, harness=PromptEchoCoder(ECHO_PROMPT))
    turn = next(e for e in observer.events if e.kind == EventKind.AI)
    assert turn.content == "do it" and result.stats.turns == 1


async def test_nonzero_exit_is_a_crash_with_stderr() -> None:
    observer = Recorder()
    with pytest.raises(CoderCrashed) as exc:
        await run(
            job(),
            observer,
            harness=ScriptedCoder(f"cat {FIXTURE}; echo boom >&2; exit 3"),
        )
    (end,) = observer.ends  # the callback hears a failed end, with the turns so far
    assert not end.done and end.result is None
    assert end.failure.startswith("CoderCrashed: ") and end.stats.turns == 2
    assert end.tokens.input == 8847 + 11718 and end.duration_sec > 0
    assert exc.value.exit_code == 3
    assert "boom" in exc.value.stderr


async def test_silence_is_a_stall_and_kills_the_coder() -> None:
    with pytest.raises(Stalled):
        await run(job(stall_sec=1), Recorder(), harness=ScriptedCoder("sleep 30"))


async def test_context_over_limit_is_context_pressure() -> None:
    with pytest.raises(ContextPressure):
        await run(
            job(context_limit_tokens=10_000),
            Recorder(),
            harness=ScriptedCoder(f"cat {FIXTURE}"),
        )


async def test_coder_sees_workdir_as_pwd(tmp_path: Path) -> None:
    script = f"echo $PWD > {tmp_path / 'pwd.txt'}; cat {FIXTURE}"
    await run(job(workdir=str(tmp_path)), Recorder(), harness=ScriptedCoder(script))
    assert (tmp_path / "pwd.txt").read_text().strip() == str(tmp_path)


class CompactingCoder(ScriptedCoder):
    """Compaction requests append a line to `marker`, so the test can count them."""

    def __init__(self, script: str, marker: Path) -> None:
        super().__init__(script)
        self.marker = marker

    def compact_command(self, session_id: str) -> list[str]:
        return ["sh", "-c", f"echo {session_id} >> {self.marker}"]


@pytest.fixture
def compact_at(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every ai turn of the fixture is above 1 token."""
    monkeypatch.setattr(settings.job, "compact_at_tokens", 1)


@pytest.mark.usefixtures("compact_at")
async def test_compaction_is_requested_once_per_threshold_crossing(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    observer = Recorder()
    await run(
        job(workdir=str(tmp_path)),  # one request, not one per turn
        observer,
        harness=CompactingCoder(f"cat {FIXTURE}", marker),
    )
    compactions = [e for e in observer.events if e.kind == EventKind.COMPACTION]
    assert len(compactions) == 1 and compactions[0].content == "compaction requested"
    assert marker.read_text().splitlines() == [compactions[0].session_id]


async def test_no_compaction_below_threshold_or_when_coder_cannot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "marker"
    await run(  # the fixture stays far below the default threshold
        job(workdir=str(tmp_path)),
        Recorder(),
        harness=CompactingCoder(f"cat {FIXTURE}", marker),
    )
    assert not marker.exists()
    monkeypatch.setattr(settings.job, "compact_at_tokens", 1)
    coder = CompactingCoder(f"cat {FIXTURE}", marker)
    coder.compacts_while_running = False  # type: ignore[misc]  # claude-like: flag, not a call
    await run(job(workdir=str(tmp_path)), Recorder(), harness=coder)
    assert not marker.exists()


async def test_resume_of_a_large_session_compacts_first(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    observer = Recorder()
    large = settings.job.compact_at_tokens + 1
    await run(
        job(workdir=str(tmp_path), session_id="old", session_tokens=large),
        observer,
        harness=CompactingCoder(f"cat {FIXTURE}", marker),
    )
    assert observer.events[0].kind == EventKind.COMPACTION  # before the coder started
    assert marker.read_text().strip() == "old"


@pytest.mark.usefixtures("compact_at")
async def test_failed_compaction_is_reported_and_the_run_goes_on(tmp_path: Path) -> None:
    observer = Recorder()
    coder = CompactingCoder(f"cat {FIXTURE}", tmp_path / "unused")
    coder.compact_command = lambda session_id: ["sh", "-c", "echo boom >&2; exit 3"]  # type: ignore[method-assign]
    result = await run(job(workdir=str(tmp_path)), observer, harness=coder)
    compactions = [e for e in observer.events if e.kind == EventKind.COMPACTION]
    assert compactions[0].content == "compaction failed: boom"
    assert result.session_id


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def child_pid(pid_file: Path) -> int:
    for _ in range(50):
        if pid_file.exists() and pid_file.read_text().strip():
            return int(pid_file.read_text())
        await asyncio.sleep(0.1)
    raise AssertionError("the coder never wrote its child's pid")


async def test_a_stall_kills_the_coder_and_its_children(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    script = f"sleep 60 & echo $! > {pid_file}; wait"
    with pytest.raises(Stalled):
        await run(job(stall_sec=1), Recorder(), harness=ScriptedCoder(script))
    assert not alive(await child_pid(pid_file))


async def test_a_callback_error_kills_the_coder_and_reaches_on_end(tmp_path: Path) -> None:
    class Broken(Recorder):
        async def on_event(self, event: Event) -> None:
            raise RuntimeError("journal down")

    pid_file = tmp_path / "child.pid"
    observer = Broken()
    script = f"sleep 60 & echo $! > {pid_file}; cat {FIXTURE}; wait"
    with pytest.raises(RuntimeError, match="journal down"):
        await run(job(), observer, harness=ScriptedCoder(script))
    (end,) = observer.ends
    assert end.failure == "RuntimeError: journal down"
    assert not alive(await child_pid(pid_file))


async def test_a_cancelled_run_kills_the_coder_and_reaches_on_end(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    observer = Recorder()
    script = f"sleep 60 & echo $! > {pid_file}; wait"
    task = asyncio.create_task(run(job(), observer, harness=ScriptedCoder(script)))
    pid = await child_pid(pid_file)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (end,) = observer.ends
    assert end.failure == "cancelled"
    assert not alive(pid)


async def test_exit_zero_without_finished_is_a_crash() -> None:
    lines = FIXTURE.read_text().splitlines()[:3]  # ends on a tool-calls step
    (tmp := Path(FIXTURE.parent) / "cut_short.tmp").write_text("\n".join(lines))
    try:
        with pytest.raises(CoderCrashed, match="without saying it finished"):
            await run(job(), Recorder(), harness=ScriptedCoder(f"cat {tmp}"))
    finally:
        tmp.unlink()


async def test_a_dropped_last_line_gives_a_result_with_usage_unknown() -> None:
    """opencode lost its final `step_finish`: the run still ends, with the
    turns seen so far summed and the totals marked as not known."""
    cut = FIXTURE.parent / "cut.jsonl"
    result = await run(job(), Recorder(), harness=ScriptedCoder(f"cat {cut}"))
    assert not result.usage_known
    assert result.tokens.input > 0  # the earlier turns carried their usage


async def test_usage_lost_at_exit_is_read_back_from_the_coders_record(tmp_path: Path) -> None:
    cut = FIXTURE.parent / "cut.jsonl"
    messages_made_now(record := tmp_path / "messages.json")
    harness = CoderWithRecord(f"cat {cut}", f"cat {record}")
    observer = Recorder()
    result = await run(job(), observer, harness=harness)
    assert result.usage_known
    assert [e.kind for e in observer.events][-2:] == [EventKind.FINISHED, EventKind.USAGE]
    assert observer.events[-1].usage == result.tokens  # the journal has the read-back too
    assert result.tokens == Tokens(input=9862 + 3264, output=69 + 11, cache_read=9841)
    assert result.cost_usd == pytest.approx(0.0011444 + 0.000354482)


async def test_a_failed_read_back_leaves_the_usage_unknown() -> None:
    cut = FIXTURE.parent / "cut.jsonl"
    harness = CoderWithRecord(f"cat {cut}", "echo nope >&2; exit 3")
    result = await run(job(), Recorder(), harness=harness)
    assert not result.usage_known and result.tokens.input > 0


async def test_a_read_back_that_is_not_the_record_leaves_the_usage_unknown() -> None:
    cut = FIXTURE.parent / "cut.jsonl"
    harness = CoderWithRecord(f"cat {cut}", "echo not json")
    result = await run(job(), Recorder(), harness=harness)
    assert not result.usage_known


async def test_a_stream_with_totals_does_not_read_back(tmp_path: Path) -> None:
    harness = CoderWithRecord(f"cat {FIXTURE}", "exit 9")  # would fail if it ran
    result = await run(job(), Recorder(), harness=harness)
    assert result.usage_known and result.tokens.input == 8847 + 11718
