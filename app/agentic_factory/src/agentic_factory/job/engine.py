import asyncio
import contextlib
from asyncio.subprocess import Process
from collections.abc import Awaitable, Callable
from time import monotonic

from agentic_factory.callback import Callback, JobEnd
from agentic_factory.event import Event
from agentic_factory.failure import CoderCrashed, JobFailed, Stalled, TimedOut
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.context import ContextWatch, compact
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.ledger import Ledger
from agentic_factory.job.process.spawn import start_process
from agentic_factory.job.process.tail import tail_of
from agentic_factory.job.process.workdir import ensure_workdir
from agentic_factory.job.session import create_session
from agentic_factory.job.summary.contract import JobSummary
from agentic_factory.job.summary.parse import parse_summary
from agentic_factory.job.summary.prompt import wrap_prompt
from agentic_factory.settings.load import settings

Repair = Callable[[str], Awaitable[JobSummary | None]]


CANCELLED = "cancelled"  # the failure text of a run that was cancelled from outside


async def run(job: Job, callback: Callback, harness: Harness, repair: Repair) -> JobResult:
    """Run one llm job to its end: give it its model, workdir and session,
    tell the callback it starts, compact a large session before resuming it,
    run the coder while feeding every event to the callback, and either return
    the result or raise the `JobFailed` subclass that says why there is none.
    The callback hears the end either way, with the totals so far. A summary
    block that does not parse goes to `repair`, one model step, before the
    result is made. The caller picks the harness (`harness_for`) and the
    repair (`repair_summary`)."""
    job = with_default_model(job, harness)
    ensure_workdir(job)
    job = await _with_session(job, harness)
    await callback.on_start(job)
    ledger = Ledger()
    started = monotonic()
    try:
        result = await _result_of_run(job, harness, callback, repair, ledger, started)
    except (JobFailed, asyncio.CancelledError) as failure:
        await callback.on_end(_end_of(ledger, started, failure=_failure_text(failure)))
        raise
    await callback.on_end(_end_of(ledger, started, result=result))
    return result


async def _result_of_run(
    job: Job, harness: Harness, callback: Callback, repair: Repair, ledger: Ledger, started: float
) -> JobResult:
    """The run itself: the compaction, the coder to its end, the summary, the result."""
    await _compact_if_large(job, harness, callback)
    await _run_coder(job, harness, callback, started, ledger)
    summary = await _parse_or_repair_summary(ledger, repair)
    return _job_result(ledger, summary, monotonic() - started)


def _failure_text(failure: BaseException) -> str:
    if isinstance(failure, asyncio.CancelledError):
        return CANCELLED
    return f"{type(failure).__name__}: {failure}"


def _end_of(
    ledger: Ledger, started: float, result: JobResult | None = None, failure: str = ""
) -> JobEnd:
    return JobEnd(
        result=result,
        failure=failure,
        tokens=ledger.tokens,
        cost_usd=ledger.cost_usd,
        duration_sec=monotonic() - started,
        stats=ledger.stats,
    )


async def _with_session(job: Job, harness: Harness) -> Job:
    """The job with a session: its own, or one made here when it has none
    (a direct run; a workflow makes it before try 1)."""
    if job.session_id:
        return job
    return job.model_copy(update={"session_id": await create_session(job, harness)})


async def _compact_if_large(job: Job, harness: Harness, callback: Callback) -> None:
    """A session resumed past the compaction threshold is compacted first."""
    if job.session_tokens >= settings.job.compact_at_tokens:
        await compact(harness, job, job.session_id, callback)


async def _run_coder(
    job: Job, harness: Harness, callback: Callback, started: float, ledger: Ledger
) -> None:
    """Start the coder and read it to the end into the ledger, killing it on
    any failure or cancellation. Raises `CoderCrashed` when it died or never
    said it finished."""
    proc = await _start_coder(job, harness)
    stderr_task = asyncio.create_task(_stderr_tail(proc))
    try:
        await _read_events(proc, job, harness, callback, started, ledger)
        exit_code = await proc.wait()
    except (JobFailed, asyncio.CancelledError):
        await _kill_coder(proc)
        raise
    _raise_unless_finished(exit_code, await stderr_task, ledger)


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
    callback: Callback,
    started: float,
    ledger: Ledger,
) -> None:
    """Read stdout until it closes: every line becomes events for the callback,
    the ledger and the context watch. Stops on the job's timeout or stall."""
    deadline = started + job.timeout_sec
    watch = ContextWatch(job, harness, callback)
    while True:
        data = await _read_line_within_limits(proc, job, deadline)
        for event in _events_of(data, harness):
            await callback.on_event(event)
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
        tokens=ledger.tokens,
        cost_usd=ledger.cost_usd,
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
