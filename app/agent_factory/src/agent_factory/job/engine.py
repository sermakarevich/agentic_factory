import asyncio
import contextlib
import os
from asyncio.subprocess import DEVNULL, PIPE, Process
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from agent_factory.event import Event, EventKind, Observer
from agent_factory.failure import CoderCrashed, ContextPressure, JobFailed, Stalled, TimedOut
from agent_factory.job.catalog import harness_for
from agent_factory.job.contract import Job, JobResult
from agent_factory.job.harness import Harness
from agent_factory.job.ledger import Ledger
from agent_factory.job.repair import repair_summary
from agent_factory.job.session import create_session
from agent_factory.job.summary import JobSummary, parse_summary, wrap_prompt
from agent_factory.settings.load import settings
from agent_factory.tokens import Tokens

Repair = Callable[[str], Awaitable[JobSummary | None]]


async def run(
    job: Job,
    observer: Observer,
    harness: Harness | None = None,
    repair: Repair = repair_summary,
) -> JobResult:
    """Run one llm job to its end: start the coder, feed every event to the
    observer, enforce the job's limits, and either return the result or raise
    the `JobFailed` subclass that says why there is none. A summary block that
    does not parse goes to `repair`, one model step, before the result is made.
    The coder always runs in a named session: the job's, or one made here
    when the job has none (a direct run; a workflow makes it before try 1)."""
    harness = harness or harness_for(job.provider)
    if not job.model:
        job = job.model_copy(update={"model": harness.default_model})
    started = monotonic()
    Path(job.workdir).mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PWD": job.workdir}  # opencode reads PWD, not the real cwd
    if not job.session_id:
        job = job.model_copy(update={"session_id": await create_session(job, harness)})
    if job.session_tokens >= settings.job.compact_at_tokens:
        await compact(harness, job, job.session_id, env, observer)
    ledger = Ledger()
    proc = await asyncio.create_subprocess_exec(
        *harness.command(job.model_copy(update={"prompt": wrap_prompt(job.prompt)})),
        cwd=job.workdir,
        env=env,
        stdin=DEVNULL,  # claude waits for piped input when stdin is open
        stdout=PIPE,
        stderr=PIPE,
        limit=settings.job.line_limit_bytes,
    )
    stderr_task = asyncio.create_task(_stderr_tail(proc, settings.job.failure_tail_chars))
    try:
        await _read_events(proc, job, harness, observer, started, env, ledger)
        exit_code = await proc.wait()
    except (JobFailed, asyncio.CancelledError):
        await _kill(proc)
        raise
    stderr = await stderr_task
    if exit_code != 0:
        raise CoderCrashed(exit_code, stderr)
    if ledger.finished is None:
        raise CoderCrashed(exit_code, f"exited without saying it finished\n{stderr}")
    summary = parse_summary(ledger.summary_block) if ledger.summary_block else None
    if ledger.summary_block and summary is None:
        summary = await repair(ledger.summary_block)
    return JobResult(
        session_id=ledger.finished.session_id,
        tokens=ledger.finished.usage or Tokens(),
        cost_usd=ledger.finished.cost_usd,
        duration_sec=monotonic() - started,
        stats=ledger.stats,
        summary_text=ledger.summary_block,
        summary=summary,
    )


async def _read_events(
    proc: Process,
    job: Job,
    harness: Harness,
    observer: Observer,
    started: float,
    env: dict[str, str],
    ledger: Ledger,
) -> None:
    """Read stdout until it closes, feeding every event to the observer and the ledger.
    Watches the context of every model turn: asks for a compaction once it
    passes the `compact_at_tokens` setting (when the coder allows that during a run) and
    kills the run above `context_limit_tokens`."""
    assert proc.stdout is not None
    deadline = started + job.timeout_sec
    session_id = job.session_id
    compaction_pending = False
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimedOut(f"exceeded {job.timeout_sec}s")
        try:
            data = await asyncio.wait_for(
                proc.stdout.readline(), timeout=min(job.stall_sec, remaining)
            )
        except TimeoutError:
            if monotonic() >= deadline:
                raise TimedOut(f"exceeded {job.timeout_sec}s") from None
            raise Stalled(f"no output for {job.stall_sec}s") from None
        if data:
            events = harness.parse_line(data.decode(errors="replace"))
        else:
            events = harness.end_of_stream()
        for event in events:
            await observer.on_event(event)
            ledger.add(event)
            if event.kind == EventKind.SESSION:
                session_id = event.session_id
            elif event.kind == EventKind.AI and (context := context_of(event)) is not None:
                if context > job.context_limit_tokens:
                    raise ContextPressure(
                        f"context {context} tokens > limit {job.context_limit_tokens}"
                    )
                if context < settings.job.compact_at_tokens:
                    compaction_pending = False  # it shrank; the next crossing may ask again
                elif not compaction_pending and harness.compacts_while_running and session_id:
                    compaction_pending = True
                    await compact(harness, job, session_id, env, observer)
        if not data:
            return


def context_of(event: Event) -> int | None:
    """The context size of a model turn: what it read, from the prompt or the cache."""
    if event.usage is None:
        return None
    return event.usage.input + event.usage.cache_read + event.usage.cache_write


async def compact(
    harness: Harness, job: Job, session_id: str, env: dict[str, str], observer: Observer
) -> None:
    """Ask the coder to compact the session. Best effort: a failure is reported
    as an event and the run goes on, since the context limit still guards it."""
    proc = await asyncio.create_subprocess_exec(
        *harness.compact_command(session_id),
        cwd=job.workdir,
        env=env,
        stdin=DEVNULL,
        stdout=DEVNULL,
        stderr=PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode == 0:
        outcome = "requested"
    else:
        tail = stderr[-settings.job.failure_tail_chars :].decode(errors="replace").strip()
        outcome = f"failed: {tail}"
    await observer.on_event(
        Event(
            kind=EventKind.COMPACTION,
            at=datetime.now(UTC),
            session_id=session_id,
            content=f"compaction {outcome}",
        )
    )


async def _stderr_tail(proc: Process, keep: int) -> str:
    assert proc.stderr is not None
    data = await proc.stderr.read()
    return data[-keep:].decode(errors="replace")


async def _kill(proc: Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(asyncio.CancelledError):
        await proc.wait()
