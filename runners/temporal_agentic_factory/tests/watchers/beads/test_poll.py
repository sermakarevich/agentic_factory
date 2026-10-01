"""A tick without servers: fake beads on one side, fake workflows on the other."""

from datetime import UTC, datetime

from agentic_factory.job.contract import Job
from temporal_agentic_factory.watchers.beads.client import BeadsClient, marker
from temporal_agentic_factory.watchers.beads.models import Bead, BeadState
from temporal_agentic_factory.watchers.beads.poll import AlreadySpawned, UnknownWorkflow, poll_once
from temporal_agentic_factory.watchers.beads.shell import BeadsError

NOW = datetime(2026, 10, 2, tzinfo=UTC)


class FakeBeads(BeadsClient):
    """Scripted beads: ready list, states, claim races; records mutations."""

    def __init__(
        self,
        ready: list[Bead] | None = None,
        states: list[BeadState] | None = None,
        claimed: set[str] | None = None,
    ) -> None:
        super().__init__(timeout_sec=1)
        self._ready = ready or []
        self._states = states or []
        self.taken: set[str] = set(claimed or [])
        self.comments_made: list[tuple[str, str]] = []
        self.closed: list[str] = []
        self.reopened: list[str] = []

    def ready(self) -> list[Bead]:
        return self._ready

    def in_progress(self, limit: int) -> list[BeadState]:
        return self._states[:limit]

    def comments(self, bead_id: str) -> list[str]:
        return []

    def claim(self, bead_id: str) -> None:
        if bead_id in self.taken:
            raise BeadsError(f"bd update {bead_id} failed (rc=1): already claimed")
        self.taken.add(bead_id)

    def comment(self, bead_id: str, text: str) -> None:
        self.comments_made.append((bead_id, text))

    def close(self, bead_id: str) -> None:
        self.closed.append(bead_id)

    def reopen(self, bead_id: str) -> None:
        self.reopened.append(bead_id)


class FakeFlows:
    """Scripted workflows: statuses, spawned ledger."""

    def __init__(
        self,
        statuses: dict[str, str] | None = None,
        known: set[str] | None = None,
    ) -> None:
        self.statuses = statuses or {}
        self.known = set(known or [])
        self.spawned: list[str] = []

    async def spawn(self, bead_id: str, job: Job) -> str:
        if bead_id in self.known:
            raise AlreadySpawned(bead_id)
        self.spawned.append(bead_id)
        wid = f"bead-{bead_id}"
        self.known.add(bead_id)
        self.statuses[wid] = "RUNNING"
        return wid

    async def status_of(self, workflow_id: str) -> str:
        if workflow_id not in self.statuses:
            raise UnknownWorkflow(workflow_id)
        return self.statuses[workflow_id]

    async def result_text(self, workflow_id: str) -> str:
        return "session ses_1, verdict done"

    async def exists(self, bead_id: str) -> bool:
        return bead_id in self.known


def _bead(bead_id: str, coder: str = "opencode") -> Bead:
    return Bead(id=bead_id, title="Do it", description="Details.", coder=coder, cwd="/tmp")


async def test_spawn_claims_starts_and_marks() -> None:
    beads = FakeBeads(ready=[_bead("bd-1")])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.spawned == ["bd-1"]
    assert "bd-1" in beads.taken
    assert ("bd-1", marker("bead-bd-1")) in beads.comments_made


async def test_spawns_stop_at_the_batch_limit() -> None:
    beads = FakeBeads(ready=[_bead(f"bd-{n}") for n in range(10)])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, 6, 600, NOW)
    assert summary.spawned == [f"bd-{n}" for n in range(6)]


async def test_unmapped_coder_never_claimed() -> None:
    beads = FakeBeads(ready=[_bead("bd-1", coder="codex")])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.spawned == []
    assert beads.taken == set()
    assert "codex" in summary.skipped["bd-1"]


async def test_lost_claim_race_is_skipped() -> None:
    beads = FakeBeads(ready=[_bead("bd-1")], claimed={"bd-1"})
    flows = FakeFlows()
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.spawned == []
    assert flows.spawned == []


async def test_completed_bead_commented_and_closed() -> None:
    beads = FakeBeads(states=[BeadState(id="bd-1", comments=["[af] workflow bead-bd-1"])])
    flows = FakeFlows(statuses={"bead-bd-1": "COMPLETED"})
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.closed == ["bd-1"]
    assert beads.closed == ["bd-1"]


async def test_failed_bead_left_open_with_a_note() -> None:
    beads = FakeBeads(states=[BeadState(id="bd-1", comments=["[af] workflow bead-bd-1"])])
    flows = FakeFlows(statuses={"bead-bd-1": "FAILED"})
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.closed == []
    assert beads.closed == []
    assert "FAILED" in summary.skipped["bd-1"]


async def test_old_markerless_bead_reopened() -> None:
    beads = FakeBeads(
        states=[BeadState(id="bd-1", updated_at="2026-10-01T10:00:00+00:00", comments=[])]
    )
    flows = FakeFlows()
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.reopened == ["bd-1"]
    assert beads.reopened == ["bd-1"]


async def test_young_markerless_bead_untouched() -> None:
    beads = FakeBeads(
        states=[BeadState(id="bd-1", updated_at="2026-10-02T11:59:00+00:00", comments=[])]
    )
    flows = FakeFlows()
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.reopened == []


async def test_marker_without_workflow_is_skipped() -> None:
    beads = FakeBeads(states=[BeadState(id="bd-1", comments=["[af] workflow bead-gone"])])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, 10, 600, NOW)
    assert summary.closed == []
    assert "no such workflow" in summary.skipped["bd-1"]
