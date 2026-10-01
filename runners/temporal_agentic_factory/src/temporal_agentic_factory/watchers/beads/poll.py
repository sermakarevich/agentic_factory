"""One tick: reconcile finished beads, then claim ready ones and spawn their jobs.

State lives in beads comments (`[af] workflow ...` markers) and workflow ids
(`bead-<id>`), so overlapping ticks are safe: the claim absorbs races for
new beads, the workflow id absorbs them for spawns.
"""

from collections.abc import Collection
from datetime import UTC, datetime
from typing import Protocol

from agentic_factory.job.contract import Job
from temporal_agentic_factory.watchers.beads.client import BeadsClient, marker, marker_for
from temporal_agentic_factory.watchers.beads.mapping import decide, workflow_id
from temporal_agentic_factory.watchers.beads.models import Bead, PollSummary
from temporal_agentic_factory.watchers.beads.shell import BeadsError

TERMINAL = ("COMPLETED", "FAILED", "TIMED_OUT", "TERMINATED", "CANCELED")


class Workflows(Protocol):
    """The Temporal side of a tick; the activity implements it for real."""

    async def spawn(self, bead_id: str, job: Job) -> str:
        """Start the bead's job workflow; its id. Raises AlreadySpawned on conflict."""
        ...

    async def status_of(self, workflow_id: str) -> str:
        """RUNNING, COMPLETED, FAILED, ...; raises UnknownWorkflow when absent."""
        ...

    async def result_text(self, workflow_id: str) -> str: ...

    async def exists(self, bead_id: str) -> bool:
        """Whether any tick spawned this bead (its `bead-<id>` workflow resolves)."""
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
    """Finished beads closed, orphans released; running ones left alone."""
    try:
        states = beads.in_progress(limit=100)
    except BeadsError as error:
        summary.errors.append(f"in_progress list failed: {error}")
        return
    for state in states:
        wid = marker_for(state.comments)
        if wid is None:
            await _release_if_orphan(
                beads, flows, summary, state.id, state.updated_at, orphan_timeout_sec, now
            )
            continue
        try:
            status = await flows.status_of(wid)
        except UnknownWorkflow:
            summary.skipped[state.id] = f"marked {wid} but no such workflow"
            continue
        except Exception as error:
            summary.errors.append(f"describe {wid} failed: {error}")
            continue
        if status not in TERMINAL:
            continue
        if status == "COMPLETED":
            await _closed(beads, flows, summary, state.id, wid)
        else:
            beads.comment(state.id, f"[af] workflow {wid} ended {status}; left in_progress")
            summary.skipped[state.id] = f"workflow {status}"


async def _closed(
    beads: BeadsClient, flows: Workflows, summary: PollSummary, bead_id: str, wid: str
) -> None:
    """A completed workflow's bead commented and closed."""
    try:
        text = await flows.result_text(wid)
    except Exception as error:
        summary.errors.append(f"result of {wid} failed: {error}")
        return
    beads.comment(bead_id, f"[af] done: {text}")
    try:
        beads.close(bead_id)
    except BeadsError as error:
        summary.errors.append(f"close {bead_id} failed: {error}")
        return
    summary.closed.append(bead_id)


async def _release_if_orphan(
    beads: BeadsClient,
    flows: Workflows,
    summary: PollSummary,
    bead_id: str,
    updated_at: str,
    orphan_timeout_sec: int,
    now: datetime,
) -> None:
    """An in_progress bead with no marker and no workflow this old was claimed
    by a tick that died before spawning: release it back to open."""
    try:
        if await flows.exists(bead_id):
            return
    except Exception:
        return
    if not _older_than(updated_at, orphan_timeout_sec, now):
        return
    try:
        beads.reopen(bead_id)
    except BeadsError as error:
        summary.errors.append(f"reopen {bead_id} failed: {error}")
        return
    beads.comment(bead_id, "[af] released an orphaned claim (no workflow spawned)")
    summary.reopened.append(bead_id)


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
    """One ready bead claimed, its job started and marked; or why not, in the summary."""
    decision = decide(bead, providers)
    if decision.job is None:
        summary.skipped[bead.id] = decision.skip
        return
    try:
        beads.claim(bead.id)
    except BeadsError:
        return  # lost the race; another puller took it
    try:
        wid = await flows.spawn(bead.id, decision.job)
    except AlreadySpawned:
        summary.skipped[bead.id] = f"workflow {workflow_id(bead.id)} already runs"
        return
    except Exception as error:
        summary.errors.append(f"spawn {bead.id} failed: {error}")
        return
    beads.comment(bead.id, marker(wid))
    summary.spawned.append(bead.id)
