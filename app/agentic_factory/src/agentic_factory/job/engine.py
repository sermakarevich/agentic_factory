import asyncio
from asyncio.subprocess import Process
from datetime import UTC, datetime
from time import monotonic

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import CoderCrashed, Stalled, TimedOut
from agentic_factory.job.callback import JobCallback, JobEnd
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.context import ContextWatch, compact
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.ledger import Ledger
from agentic_factory.job.process.kill import kill_process
from agentic_factory.job.process.spawn import start_process
from agentic_factory.job.process.tail import tail_of
from agentic_factory.job.process.workdir import ensure_workdir
from agentic_factory.job.session import create_session
from agentic_factory.job.usage import recover_usage
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Usage

CANCELLED = "cancelled"  # the failure text of a run that was cancelled from outside


async def run(job: Job, callback: JobCallback, harness: Harness) -> JobResult:
    """Run one llm job to its end: give it its model, workdir and session,
    tell the callback it starts, compact a large session before resuming it,
    run the coder while feeding every event to the callback, and either return
    the result or raise the `JobFailed` subclass that says why there is none.
    The callback hears the end either way, with the totals so far: on a
    result, on a `JobFailed`, on any other error and on a cancellation. The
    prompt goes to the coder as it is: the caller adds the submit request
    (`ask_for_submission`). The caller picks the harness (`harness_for`)."""
    job = with_default_model(job, harness)
    ensure_workdir(job)
    job = await _with_session(job, harness)
    await callback.on_start(job)
    ledger = Ledger()
    started = monotonic()
    try:
        result = await _coder_result(job, harness, callback, ledger, started)
    except (Exception, asyncio.CancelledError) as failure:
        await callback.on_end(_end_of(ledger, started, failure=_failure_text(failure)))
        raise
    await callback.on_end(_end_of(ledger, started, result=result))
    return result


async def _coder_result(
    job: Job,
    harness: Harness,
    callback: JobCallback,
    ledger: Ledger,
    started: float,
) -> JobResult:
    """The run itself: the compaction, the coder to its end, the usage it
    lost read back, the result."""
    await _compact_if_large(job, harness, callback)
    since = datetime.now(UTC)
    await _read_coder(job, harness, callback, started, ledger)
    await _recover_usage_if_unknown(job, harness, callback, ledger, since)
    return _job_result(ledger, monotonic() - started)


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


async def _compact_if_large(job: Job, harness: Harness, callback: JobCallback) -> None:
    """A session resumed past the compaction threshold is compacted first."""
    if job.session_tokens >= settings.job.compact_at_tokens:
        await compact(harness, job, job.session_id, callback)


async def _read_coder(
    job: Job, harness: Harness, callback: JobCallback, started: float, ledger: Ledger
) -> None:
    """Start the coder and read it to its end into the ledger. Whatever ends
    the read, the coder is killed with its children, unless it has exited,
    and nothing waits for it longer than `exit_wait_sec`. Raises `CoderCrashed`
    when it died, hung after closing its output, or never said it finished."""
    proc = await _start_coder(job, harness)
    stderr_task = asyncio.create_task(_stderr_tail(proc))
    try:
        await _read_events(proc, job, harness, callback, started, ledger)
        exit_code = await _exit_code_within_limit(proc)
        stderr = await _stderr_within_limit(stderr_task)
    finally:
        await kill_process(proc, settings.job.exit_wait_sec)  # nothing once it has exited
        stderr_task.cancel()  # nothing once it is done
    _raise_unless_finished(exit_code, stderr, ledger)


async def _exit_code_within_limit(proc: Process) -> int:
    """The coder's exit code once its output has closed; `CoderCrashed` when
    it stays alive past `exit_wait_sec` (it is killed by the caller)."""
    try:
        return await asyncio.wait_for(proc.wait(), settings.job.exit_wait_sec)
    except TimeoutError:
        raise CoderCrashed(
            -1, f"still running {settings.job.exit_wait_sec}s after its output closed"
        ) from None


async def _stderr_within_limit(stderr_task: asyncio.Task[str]) -> str:
    """The tail of stderr; empty when something still holds the pipe open past
    `exit_wait_sec` after the coder exited."""
    try:
        return await asyncio.wait_for(asyncio.shield(stderr_task), settings.job.exit_wait_sec)
    except TimeoutError:
        return ""


async def _start_coder(job: Job, harness: Harness) -> Process:
    """The coder process, in the workdir, with the job's prompt."""
    argv = harness.command(job)
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
    callback: JobCallback,
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


async def _recover_usage_if_unknown(
    job: Job, harness: Harness, callback: JobCallback, ledger: Ledger, since: datetime
) -> None:
    """The coder's own totals for the turns of this try, when its stream did
    not carry them: a `usage` event, to the callback and the ledger like any
    other, so the journal has it too. The partial sum stays when there are none."""
    if ledger.usage_known:
        return
    usage = await recover_usage(harness, job, since)
    if usage is None:
        return
    event = _usage_event(job.session_id, usage)
    await callback.on_event(event)
    ledger.add(event)


def _usage_event(session_id: str, usage: Usage) -> Event:
    return Event(
        kind=EventKind.USAGE,
        at=datetime.now(UTC),
        session_id=session_id,
        content="read back from the coder",
        usage=usage.tokens,
        cost_usd=usage.cost_usd,
    )


def _job_result(ledger: Ledger, duration_sec: float) -> JobResult:
    assert ledger.finished is not None
    return JobResult(
        session_id=ledger.finished.session_id,
        tokens=ledger.tokens,
        cost_usd=ledger.cost_usd,
        usage_known=ledger.usage_known,
        duration_sec=duration_sec,
        stats=ledger.stats,
    )


async def _stderr_tail(proc: Process) -> str:
    assert proc.stderr is not None
    return tail_of(await proc.stderr.read())
