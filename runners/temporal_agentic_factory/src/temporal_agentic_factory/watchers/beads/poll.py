"""One tick: reconcile finished beads, then claim ready ones and spawn their jobs.

State lives in beads comments (`[af] workflow ...` markers, `[af] retry`) and
workflow ids (`bead-<id>-<attempt>`), so overlapping ticks are safe: the claim
absorbs races for new beads, the workflow id absorbs them for spawns. A
finished bead is closed or blocked, so it leaves in_progress and is commented
once; a ready bead that cannot become a job is commented once per reason.
"""

from collections.abc import Collection
from datetime import UTC, datetime
from typing import Protocol

from agentic_factory.job.contract import Job
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.structured_output.contract import Schema
from temporal_agentic_factory.watchers.beads.client import BeadsClient
from temporal_agentic_factory.watchers.beads.ending import (
    COMPLETED,
    Ending,
    ending_of_completed,
    ending_of_stopped,
)
from temporal_agentic_factory.watchers.beads.mapping import decide, workflow_id
from temporal_agentic_factory.watchers.beads.markers import (
    attempt_of,
    blocked,
    done,
    marker,
    marker_for,
    skipped,
)
from temporal_agentic_factory.watchers.beads.models import Bead, BeadState, PollSummary
from temporal_agentic_factory.watchers.beads.shell import BeadsError

TERMINAL = (COMPLETED, "FAILED", "TIMED_OUT", "TERMINATED", "CANCELED")


class Workflows(Protocol):
    """The Temporal side of a tick; the activity implements it for real."""

    async def spawn(self, workflow_id: str, job: Job, output_schema: Schema | None) -> str:
        """Start the job workflow (with structured output when a schema is given);
        its id. Raises AlreadySpawned on conflict."""
        ...

    async def status_of(self, workflow_id: str) -> str:
        """RUNNING, COMPLETED, FAILED, ...; raises UnknownWorkflow when absent."""
        ...

    async def outcome_of(self, workflow_id: str) -> JobOutcome:
        """The job outcome a completed workflow returned."""
        ...

    async def exists(self, workflow_id: str) -> bool:
        """Whether a workflow with this id resolves, whatever its status."""
        ...


class AlreadySpawned(Exception):
    """The bead's workflow id is already taken: a previous tick spawned it."""


class UnknownWorkflow(Exception):
    """No workflow with this id: never spawned, or long gone."""


async def poll_once(
    beads: BeadsClient,
    flows: Workflows,
    providers: Collection[str],
    batch_limit: int,
    orphan_timeout_sec: int,
    now: datetime,
) -> PollSummary:
    """Reconcile, then spawn: the summary of what this tick did. Only beads for
    one of `providers` are spawned."""
    summary = PollSummary()
    await _reconcile(beads, flows, summary, orphan_timeout_sec, now)
    await _spawn(beads, flows, summary, providers, batch_limit)
    return summary


async def _reconcile(
    beads: BeadsClient,
    flows: Workflows,
    summary: PollSummary,
    orphan_timeout_sec: int,
    now: datetime,
) -> None:
    """Finished beads closed or blocked, orphans released; running ones left alone."""
    try:
        states = beads.in_progress(limit=100)
    except BeadsError as error:
        summary.errors.append(f"in_progress list failed: {error}")
        return
    for state in states:
        await _reconciled_one(beads, flows, summary, state, orphan_timeout_sec, now)


async def _reconciled_one(
    beads: BeadsClient,
    flows: Workflows,
    summary: PollSummary,
    state: BeadState,
    orphan_timeout_sec: int,
    now: datetime,
) -> None:
    """One in_progress bead: settled when its workflow ended, released when it
    has none and is old enough, else left alone."""
    wid = marker_for(state.comments)
    if wid is None:
        try:
            wid = await _unmarked_spawn(beads, flows, state)
        except Exception:
            return  # Temporal cannot say whether it runs: neither settled nor released
    if wid is None:
        _release_if_orphan(beads, summary, state, orphan_timeout_sec, now)
        return
    try:
        status = await flows.status_of(wid)
    except UnknownWorkflow:
        summary.skipped[state.id] = f"marked {wid} but no such workflow"
        return
    except Exception as error:
        summary.errors.append(f"describe {wid} failed: {error}")
        return
    if status not in TERMINAL:
        return
    try:
        ending = await _ending(flows, wid, status)
    except Exception as error:
        summary.errors.append(f"result of {wid} failed: {error}")
        return
    _settled(beads, summary, state.id, ending)


async def _unmarked_spawn(beads: BeadsClient, flows: Workflows, state: BeadState) -> str | None:
    """The current attempt's workflow when a spawn started it but its marker
    was never written; the marker is written now. None when there is none."""
    wid = workflow_id(state.id, attempt_of(state.comments))
    if not await flows.exists(wid):
        return None
    beads.comment(state.id, marker(wid))
    return wid


async def _ending(flows: Workflows, wid: str, status: str) -> Ending:
    """What the ended workflow means for its bead."""
    if status == COMPLETED:
        return ending_of_completed(await flows.outcome_of(wid))
    return ending_of_stopped(wid, status)


def _settled(beads: BeadsClient, summary: PollSummary, bead_id: str, ending: Ending) -> None:
    """The bead closed or blocked, then commented once; a failed status change
    is retried next tick, before any comment is left."""
    try:
        if ending.close:
            beads.close(bead_id)
        else:
            beads.block(bead_id)
    except BeadsError as error:
        summary.errors.append(f"{'close' if ending.close else 'block'} {bead_id} failed: {error}")
        return
    beads.comment(bead_id, done(ending.note) if ending.close else blocked(ending.note))
    (summary.closed if ending.close else summary.blocked).append(bead_id)


def _release_if_orphan(
    beads: BeadsClient,
    summary: PollSummary,
    state: BeadState,
    orphan_timeout_sec: int,
    now: datetime,
) -> None:
    """An in_progress bead with no marker and no workflow this old was claimed
    by a tick that died before spawning: release it back to open."""
    if not _older_than(state.updated_at, orphan_timeout_sec, now):
        return
    try:
        beads.reopen(state.id)
    except BeadsError as error:
        summary.errors.append(f"reopen {state.id} failed: {error}")
        return
    beads.comment(state.id, "[af] released an orphaned claim (no workflow spawned)")
    summary.reopened.append(state.id)


def _older_than(updated_at: str, timeout_sec: int, now: datetime) -> bool:
    """True when the bead's update stamp is past the timeout; unknown stamps never qualify."""
    try:
        updated = datetime.fromisoformat(updated_at)
    except ValueError:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return (now - updated).total_seconds() > timeout_sec


async def _spawn(
    beads: BeadsClient,
    flows: Workflows,
    summary: PollSummary,
    providers: Collection[str],
    batch_limit: int,
) -> None:
    """Ready beads claimed and spawned, up to the batch; their coder runs wait
    in their provider's queue for a free slot."""
    try:
        candidates = beads.ready(batch_limit)
    except BeadsError as error:
        summary.errors.append(f"ready list failed: {error}")
        return
    for bead in candidates:
        await _spawned_one(beads, flows, summary, providers, bead)


async def _spawned_one(
    beads: BeadsClient,
    flows: Workflows,
    summary: PollSummary,
    providers: Collection[str],
    bead: Bead,
) -> None:
    """One ready bead claimed, its job started under the attempt's id and
    marked; or why not, in the summary."""
    decision = decide(bead, providers)
    comments = beads.comments(bead.id)
    if decision.job is None:
        _skipped(beads, summary, bead.id, decision.skip, comments)
        return
    try:
        beads.claim(bead.id)
    except BeadsError:
        return  # lost the race; another puller took it
    wid = workflow_id(bead.id, attempt_of(comments))
    try:
        await flows.spawn(wid, decision.job, decision.output_schema)
    except AlreadySpawned:
        summary.skipped[bead.id] = f"workflow {wid} already runs"
        return
    except Exception as error:
        summary.errors.append(f"spawn {bead.id} failed: {error}")
        return
    beads.comment(bead.id, marker(wid))
    summary.spawned.append(bead.id)


def _skipped(
    beads: BeadsClient, summary: PollSummary, bead_id: str, reason: str, comments: list[str]
) -> None:
    """The reason in the summary every tick, on the bead only the first time."""
    summary.skipped[bead_id] = reason
    if skipped(reason) not in comments:
        beads.comment(bead_id, skipped(reason))
