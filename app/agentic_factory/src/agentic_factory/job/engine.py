import asyncio
import contextlib
from asyncio.subprocess import Process
from collections.abc import Awaitable, Callable
from time import monotonic

from agentic_factory.event import Event, Observer
from agentic_factory.failure import CoderCrashed, JobFailed, Stalled, TimedOut
from agentic_factory.job.context import ContextWatch, compact
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.harness import Harness
from agentic_factory.job.ledger import Ledger
from agentic_factory.job.session import create_session
from agentic_factory.job.spawn import start_process
from agentic_factory.job.summary import JobSummary
from agentic_factory.job.summary_parse import parse_summary
from agentic_factory.job.summary_prompt import wrap_prompt
from agentic_factory.job.tail import tail_of
from agentic_factory.job.workdir import ensure_workdir
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
    job = with_default_model(job, harness)
    ensure_workdir(job)
    job = await _with_session(job, harness)
    started = monotonic()
    await _compact_if_large(job, harness, observer)
    ledger = await _run_coder(job, harness, observer, started)
    summary = await _parse_or_repair_summary(ledger, repair)
    return _job_result(ledger, summary, monotonic() - started)


async def _with_session(job: Job, harness: Harness) -> Job:
    """The job with a session: its own, or one made here when it has none
    (a direct run; a workflow makes it before try 1)."""
    if job.session_id:
        return job
    return job.model_copy(update={"session_id": await create_session(job, harness)})


async def _compact_if_large(job: Job, harness: Harness, observer: Observer) -> None:
    """A session resumed past the compaction threshold is compacted first."""
    if job.session_tokens >= settings.job.compact_at_tokens:
        await compact(harness, job, job.session_id, observer)


async def _run_coder(job: Job, harness: Harness, observer: Observer, started: float) -> Ledger:
    """Start the coder and read it to the end, killing it on any failure or
    cancellation. Returns the ledger of what it said; raises `CoderCrashed`
    when it died or never said it finished."""
    ledger = Ledger()
    proc = await _start_coder(job, harness)
    stderr_task = asyncio.create_task(_stderr_tail(proc))
    try:
        await _read_events(proc, job, harness, observer, started, ledger)
        exit_code = await proc.wait()
    except (JobFailed, asyncio.CancelledError):
        await _kill_coder(proc)
        raise
    _raise_unless_finished(exit_code, await stderr_task, ledger)
    return ledger


async def _start_coder(job: Job, harness: Harness) -> Process:
    """The coder process, in the workdir, with the wrapped prompt."""
    argv = harness.command(job.model_copy(update={"prompt": wrap_prompt(job.prompt)}))
    return await start_process(argv, job.workdir, limit=settings.job.line_limit_bytes)


def _raise_unless_finished(exit_code: int, stderr: str, ledger: Ledger) -> None:
    """`CoderCrashed` when the coder died, or ended without saying it finished."""
    if exit_code != 0:
        raise CoderCrashed(exit_code, stderr)
    if ledger.finished is None:
        raise CoderCrashed(exit_code, f"exited without saying it finished\n{stderr}")


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
        for event in _events_of(data, harness):
            await observer.on_event(event)
            ledger.add(event)
            await watch.on_event(event)
        if not data:
            return


def _events_of(data: bytes, harness: Harness) -> list[Event]:
    """The events in one line of stdout; at its end, what the harness still holds."""
    if not data:
        return harness.end_of_stream()
    return harness.parse_line(data.decode(errors="replace"))


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


async def _stderr_tail(proc: Process) -> str:
    assert proc.stderr is not None
    return tail_of(await proc.stderr.read())


async def _kill_coder(proc: Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(asyncio.CancelledError):
        await proc.wait()
