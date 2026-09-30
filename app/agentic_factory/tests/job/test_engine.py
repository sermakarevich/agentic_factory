import json
from pathlib import Path

import pytest

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import CoderCrashed, ContextPressure, Stalled
from agentic_factory.job.contract import Job
from agentic_factory.job.engine import run
from agentic_factory.job.opencode.harness import OpencodeHarness
from agentic_factory.job.summary import JobSummary
from agentic_factory.job.summary_prompt import INSTRUCTION
from agentic_factory.settings.load import settings

FIXTURE = Path(__file__).parent / "opencode" / "fixtures" / "echo.jsonl"


async def no_repair(block: str) -> None:
    return None


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def on_event(self, event: Event) -> None:
        self.events.append(event)


class ScriptedCoder(OpencodeHarness):
    """The real opencode parser, but the process is a shell script."""

    def __init__(self, script: str) -> None:
        super().__init__()
        self.script = script

    def new_session_command(self, workdir: str) -> list[str]:
        return []  # a uuid, not a process; `command` ignores the job anyway

    def command(self, job: Job) -> list[str]:
        return ["sh", "-c", self.script]


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
    await run(job(), Recorder(), repair=no_repair, harness=SessionCoder(f"cat {FIXTURE}"))
    assert (workdir / "sess.txt").read_text().strip() == "ses_made"
    (workdir / "sess.txt").unlink()


async def test_replayed_stream_gives_result_and_events() -> None:
    observer = Recorder()
    result = await run(job(), observer, repair=no_repair, harness=ScriptedCoder(f"cat {FIXTURE}"))
    assert result.session_id.startswith("ses_")
    assert result.tokens.input == 8847 + 11718
    assert result.duration_sec > 0
    assert [e.kind for e in observer.events][-1] == EventKind.FINISHED
    assert result.stats.model_dump() == {"turns": 2, "tool_calls": 1, "tool_failures": 0}
    assert result.summary is None and result.summary_text == ""


class PromptEchoCoder(ScriptedCoder):
    """The model's text is the prompt it was given, then the coder's summary
    block: the test sees what the engine sent and how the block comes back."""

    def command(self, job: Job) -> list[str]:
        block = f"\n```json\n{json.dumps({'job_summary': SUMMARY})}\n```"
        return ["python3", "-c", self.script, job.prompt, block]


SUMMARY = {"task": "t", "plan": ["a"], "execution": ["b"], "result": "r", "success": True}
ECHO_PROMPT = """
import json, sys
line = lambda t, part: print(json.dumps({"type": t, "sessionID": "ses_1", "part": part}))
line("step_start", {"type": "step-start"})
line("text", {"type": "text", "text": sys.argv[1]})
line("text", {"type": "text", "text": sys.argv[2]})
line("step_finish", {"type": "step-finish", "reason": "stop", "tokens": {}})
"""


async def test_unparsable_block_goes_to_repair() -> None:
    class CutCoder(PromptEchoCoder):
        def command(self, job: Job) -> list[str]:
            argv = super().command(job)
            return [*argv[:-1], argv[-1][:-12]]  # the block cut mid-object, no closing fence

    repaired = JobSummary(**{**SUMMARY, "success": False})
    got: list[str] = []

    async def repair(block: str) -> JobSummary | None:
        got.append(block)
        return repaired

    result = await run(job(), Recorder(), harness=CutCoder(ECHO_PROMPT), repair=repair)
    assert got == [result.summary_text] and got[0].startswith('{"job_summary"')
    assert result.summary == repaired


async def test_prompt_is_wrapped_and_the_summary_comes_back_parsed() -> None:
    observer = Recorder()
    result = await run(
        job(prompt="do it"), observer, repair=no_repair, harness=PromptEchoCoder(ECHO_PROMPT)
    )
    turn = next(e for e in observer.events if e.kind == EventKind.AI)
    assert turn.content.startswith("do it\n\n" + INSTRUCTION)  # what the coder was sent
    assert result.summary == JobSummary(**SUMMARY)  # the coder's block, not the template
    assert result.summary_text.startswith('{"job_summary"') and result.stats.turns == 1


async def test_nonzero_exit_is_a_crash_with_stderr() -> None:
    with pytest.raises(CoderCrashed) as exc:
        await run(
            job(),
            Recorder(),
            repair=no_repair,
            harness=ScriptedCoder(f"cat {FIXTURE}; echo boom >&2; exit 3"),
        )
    assert exc.value.exit_code == 3
    assert "boom" in exc.value.stderr


async def test_silence_is_a_stall_and_kills_the_coder() -> None:
    with pytest.raises(Stalled):
        await run(job(stall_sec=1), Recorder(), repair=no_repair, harness=ScriptedCoder("sleep 30"))


async def test_context_over_limit_is_context_pressure() -> None:
    with pytest.raises(ContextPressure):
        await run(
            job(context_limit_tokens=10_000),
            Recorder(),
            repair=no_repair,
            harness=ScriptedCoder(f"cat {FIXTURE}"),
        )


async def test_coder_sees_workdir_as_pwd(tmp_path: Path) -> None:
    script = f"echo $PWD > {tmp_path / 'pwd.txt'}; cat {FIXTURE}"
    await run(
        job(workdir=str(tmp_path)), Recorder(), repair=no_repair, harness=ScriptedCoder(script)
    )
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
        repair=no_repair,
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
        repair=no_repair,
        harness=CompactingCoder(f"cat {FIXTURE}", marker),
    )
    assert not marker.exists()
    monkeypatch.setattr(settings.job, "compact_at_tokens", 1)
    coder = CompactingCoder(f"cat {FIXTURE}", marker)
    coder.compacts_while_running = False  # type: ignore[misc]  # claude-like: flag, not a call
    await run(job(workdir=str(tmp_path)), Recorder(), repair=no_repair, harness=coder)
    assert not marker.exists()


async def test_resume_of_a_large_session_compacts_first(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    observer = Recorder()
    large = settings.job.compact_at_tokens + 1
    await run(
        job(workdir=str(tmp_path), session_id="old", session_tokens=large),
        observer,
        repair=no_repair,
        harness=CompactingCoder(f"cat {FIXTURE}", marker),
    )
    assert observer.events[0].kind == EventKind.COMPACTION  # before the coder started
    assert marker.read_text().strip() == "old"


@pytest.mark.usefixtures("compact_at")
async def test_failed_compaction_is_reported_and_the_run_goes_on(tmp_path: Path) -> None:
    observer = Recorder()
    coder = CompactingCoder(f"cat {FIXTURE}", tmp_path / "unused")
    coder.compact_command = lambda session_id: ["sh", "-c", "echo boom >&2; exit 3"]  # type: ignore[method-assign]
    result = await run(job(workdir=str(tmp_path)), observer, repair=no_repair, harness=coder)
    compactions = [e for e in observer.events if e.kind == EventKind.COMPACTION]
    assert compactions[0].content == "compaction failed: boom"
    assert result.session_id
