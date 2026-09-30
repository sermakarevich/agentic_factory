import asyncio
import contextlib
from asyncio.subprocess import DEVNULL, PIPE, Process
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic

from agentic_factory.event import Observer
from agentic_factory.failure import CoderCrashed, JobFailed, Stalled, TimedOut
from agentic_factory.job.context import ContextWatch, compact
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.environment import environment
from agentic_factory.job.harness import Harness
from agentic_factory.job.ledger import Ledger
from agentic_factory.job.session import create_session
from agentic_factory.job.summary import JobSummary, parse_summary, wrap_prompt
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Tokens

Repair = Callable[[str], Awaitable[JobSummary | None]]


async def run(job: Job, observer: Observer, harness: Harness, repair: Repair) -> JobResult:
    """Run one llm job to its end: give it its model, workdir and session,
    compact a large session before resuming it, run the coder while feeding
    every event to the observer, and either return the result or raise the
    `JobFailed` subclass that says why there is none. A summary block that
    does not parse goes to `repair`, one model step, before the result is made.
    The caller picks the harness (`harness_for`) and the repair (`repair_summary`)."""
    job = _with_default_model(job, harness)
    _make_workdir(job)
    job = await _with_session(job, harness)
    started = monotonic()
    if job.session_tokens >= settings.job.compact_at_tokens:
        await compact(harness, job, job.session_id, observer)
    ledger = await _run_coder(job, harness, observer, started)
    summary = await _parse_or_repair_summary(ledger, repair)
    return _job_result(ledger, summary, monotonic() - started)


def _with_default_model(job: Job, harness: Harness) -> Job:
    if job.model:
        return job
    return job.model_copy(update={"model": harness.default_model})


def _make_workdir(job: Job) -> None:
    Path(job.workdir).mkdir(parents=True, exist_ok=True)


async def _with_session(job: Job, harness: Harness) -> Job:
    """The job with a session: its own, or one made here when it has none
    (a direct run; a workflow makes it before try 1)."""
    if job.session_id:
        return job
    return job.model_copy(update={"session_id": await create_session(job, harness)})


async def _run_coder(job: Job, harness: Harness, observer: Observer, started: float) -> Ledger:
    """Start the coder and read it to the end, killing it on any failure or
    cancellation. Returns the ledger of what it said; raises `CoderCrashed`
    when it died or never said it finished."""
    ledger = Ledger()
    proc = await _start_coder(job, harness)
    stderr_task = asyncio.create_task(_stderr_tail(proc, settings.job.failure_tail_chars))
    try:
        await _read_events(proc, job, harness, observer, started, ledger)
        exit_code = await proc.wait()
    except (JobFailed, asyncio.CancelledError):
        await _kill_coder(proc)
        raise
    stderr = await stderr_task
    if exit_code != 0:
        raise CoderCrashed(exit_code, stderr)
    if ledger.finished is None:
        raise CoderCrashed(exit_code, f"exited without saying it finished\n{stderr}")
    return ledger


async def _start_coder(job: Job, harness: Harness) -> Process:
    """The coder process, in the workdir, with the wrapped prompt and closed stdin."""
    return await asyncio.create_subprocess_exec(
        *harness.command(job.model_copy(update={"prompt": wrap_prompt(job.prompt)})),
        cwd=job.workdir,
        env=environment(job.workdir),
        stdin=DEVNULL,  # claude waits for piped input when stdin is open
        stdout=PIPE,
        stderr=PIPE,
        limit=settings.job.line_limit_bytes,
    )


async def _read_events(
    proc: Process,
    job: Job,
    harness: Harness,
    observer: Observer,
    started: float,
    ledger: Ledger,
) -> None:
    """Read stdout until it closes: every line becomes events for the observer,
    the ledger and the context watch. Stops on the job's timeout or stall."""
    deadline = started + job.timeout_sec
    watch = ContextWatch(job, harness, observer)
    while True:
        data = await _read_line_within_limits(proc, job, deadline)
        text = data.decode(errors="replace")
        events = harness.parse_line(text) if data else harness.end_of_stream()
        for event in events:
            await observer.on_event(event)
            ledger.add(event)
            await watch.on_event(event)
        if not data:
            return


async def _read_line_within_limits(proc: Process, job: Job, deadline: float) -> bytes:
    """One line of stdout, or empty bytes at its end. Raises `TimedOut` past
    the deadline and `Stalled` when nothing arrives for `stall_sec`."""
    assert proc.stdout is not None
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimedOut(f"exceeded {job.timeout_sec}s")
    try:
        return await asyncio.wait_for(proc.stdout.readline(), timeout=min(job.stall_sec, remaining))
    except TimeoutError:
        if monotonic() >= deadline:
            raise TimedOut(f"exceeded {job.timeout_sec}s") from None
        raise Stalled(f"no output for {job.stall_sec}s") from None


async def _parse_or_repair_summary(ledger: Ledger, repair: Repair) -> JobSummary | None:
    """The coder's summary block parsed, repaired by a step when it does not
    parse, or None when the coder wrote none."""
    if not ledger.summary_block:
        return None
    return parse_summary(ledger.summary_block) or await repair(ledger.summary_block)


def _job_result(ledger: Ledger, summary: JobSummary | None, duration_sec: float) -> JobResult:
    assert ledger.finished is not None
    return JobResult(
        session_id=ledger.finished.session_id,
        tokens=ledger.finished.usage or Tokens(),
        cost_usd=ledger.finished.cost_usd,
        duration_sec=duration_sec,
        stats=ledger.stats,
        summary_text=ledger.summary_block,
        summary=summary,
    )


async def _stderr_tail(proc: Process, keep: int) -> str:
    assert proc.stderr is not None
    data = await proc.stderr.read()
    return data[-keep:].decode(errors="replace")


async def _kill_coder(proc: Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(asyncio.CancelledError):
        await proc.wait()
