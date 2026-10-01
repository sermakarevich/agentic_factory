"""A tick without servers: fake beads on one side, fake workflows on the other."""

from datetime import UTC, datetime
from pathlib import Path

from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.job.submission.contract import Schema
from temporal_agentic_factory.watchers.beads.client import BeadsClient
from temporal_agentic_factory.watchers.beads.markers import marker, retried, skipped
from temporal_agentic_factory.watchers.beads.models import Bead, BeadState
from temporal_agentic_factory.watchers.beads.poll import AlreadySpawned, UnknownWorkflow, poll_once
from temporal_agentic_factory.watchers.beads.shell import BeadsError
from tests.fake_bd import FakeBd

NOW = datetime(2026, 10, 2, tzinfo=UTC)
PROVIDERS = ["claude", "opencode"]


class FakeBeads(BeadsClient):
    """Scripted beads: ready list, states, comments, claim races; records mutations."""

    def __init__(
        self,
        ready: list[Bead] | None = None,
        states: list[BeadState] | None = None,
        claimed: set[str] | None = None,
        comments: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(Path("/nowhere"), 1, FakeBd())
        self._ready = ready or []
        self._states = states or []
        self._comments = comments or {}
        self.taken: set[str] = set(claimed or [])
        self.comments_made: list[tuple[str, str]] = []
        self.closed: list[str] = []
        self.blocked: list[str] = []
        self.reopened: list[str] = []

    def ready(self, limit: int) -> list[Bead]:
        return self._ready[:limit]

    def in_progress(self, limit: int) -> list[BeadState]:
        return self._states[:limit]

    def comments(self, bead_id: str) -> list[str]:
        return list(self._comments.get(bead_id, []))

    def claim(self, bead_id: str) -> None:
        if bead_id in self.taken:
            raise BeadsError(f"bd update {bead_id} failed (rc=1): already claimed")
        self.taken.add(bead_id)

    def comment(self, bead_id: str, text: str) -> None:
        self.comments_made.append((bead_id, text))
        self._comments.setdefault(bead_id, []).append(text)

    def close(self, bead_id: str) -> None:
        self.closed.append(bead_id)

    def block(self, bead_id: str) -> None:
        self.blocked.append(bead_id)

    def reopen(self, bead_id: str) -> None:
        self.reopened.append(bead_id)


class FakeFlows:
    """Scripted workflows: statuses, outcomes, and a ledger of spawns."""

    def __init__(
        self,
        statuses: dict[str, str] | None = None,
        outcomes: dict[str, JobOutcome] | None = None,
    ) -> None:
        self.statuses = statuses or {}
        self.outcomes = outcomes or {}
        self.spawned: list[tuple[str, Schema | None]] = []

    async def spawn(self, workflow_id: str, job: Job, output_schema: Schema | None) -> str:
        if workflow_id in self.statuses:
            raise AlreadySpawned(workflow_id)
        self.spawned.append((workflow_id, output_schema))
        self.statuses[workflow_id] = "RUNNING"
        return workflow_id

    async def status_of(self, workflow_id: str) -> str:
        if workflow_id not in self.statuses:
            raise UnknownWorkflow(workflow_id)
        return self.statuses[workflow_id]

    async def outcome_of(self, workflow_id: str) -> JobOutcome:
        return self.outcomes[workflow_id]

    async def exists(self, workflow_id: str) -> bool:
        return workflow_id in self.statuses


def _bead(bead_id: str, **job_fields: object) -> Bead:
    return Bead(
        id=bead_id,
        title="Do it",
        description="Details.",
        job_fields={"provider": "opencode", "workdir": "/tmp"} | job_fields,
    )


def _outcome(verdict: Verdict) -> JobOutcome:
    report = JobReport(task="t", done=[], not_done=["the tests"], problems=[], verdict=verdict)
    return JobOutcome(session_id="ses_1", result=JobResult(session_id="ses_1"), report=report)


def _running(bead_id: str, *comments: str) -> BeadState:
    return BeadState(id=bead_id, comments=list(comments))


async def test_spawn_claims_starts_and_marks() -> None:
    beads = FakeBeads(ready=[_bead("bd-1")])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.spawned == ["bd-1"]
    assert "bd-1" in beads.taken
    assert flows.spawned == [("bead-bd-1-1", None)]
    assert ("bd-1", marker("bead-bd-1-1")) in beads.comments_made


async def test_structured_output_bead_spawns_with_its_schema() -> None:
    schema = {"type": "object"}
    beads = FakeBeads(ready=[_bead("bd-1", structured_output=schema)])
    flows = FakeFlows()
    await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert flows.spawned == [("bead-bd-1-1", schema)]


async def test_spawns_stop_at_the_batch_limit() -> None:
    beads = FakeBeads(ready=[_bead(f"bd-{n}") for n in range(10)])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, PROVIDERS, 6, 600, NOW)
    assert summary.spawned == [f"bd-{n}" for n in range(6)]


async def test_unconfigured_provider_never_claimed() -> None:
    beads = FakeBeads(ready=[_bead("bd-1", provider="codex")])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.spawned == []
    assert beads.taken == set()
    assert "codex" in summary.skipped["bd-1"]


async def test_invalid_bead_skipped_every_tick_but_commented_once() -> None:
    beads = FakeBeads(ready=[_bead("bd-1", colour="blue")])
    flows = FakeFlows()
    first = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    second = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert "colour" in first.skipped["bd-1"]
    assert second.skipped == first.skipped
    assert beads.comments_made == [("bd-1", skipped(first.skipped["bd-1"]))]
    assert beads.taken == set()


async def test_lost_claim_race_is_skipped() -> None:
    beads = FakeBeads(ready=[_bead("bd-1")], claimed={"bd-1"})
    flows = FakeFlows()
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.spawned == []
    assert flows.spawned == []


async def test_done_verdict_closes_with_one_comment() -> None:
    beads = FakeBeads(states=[_running("bd-1", marker("bead-bd-1-1"))])
    flows = FakeFlows(
        statuses={"bead-bd-1-1": "COMPLETED"}, outcomes={"bead-bd-1-1": _outcome(Verdict.DONE)}
    )
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.closed == ["bd-1"]
    assert beads.closed == ["bd-1"]
    assert beads.blocked == []
    assert [text for _, text in beads.comments_made] == ["[af] done: session ses_1, verdict done"]


async def test_completed_without_done_verdict_blocks() -> None:
    beads = FakeBeads(states=[_running("bd-1", marker("bead-bd-1-1"))])
    flows = FakeFlows(
        statuses={"bead-bd-1-1": "COMPLETED"},
        outcomes={"bead-bd-1-1": _outcome(Verdict.PARTIAL)},
    )
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.blocked == ["bd-1"]
    assert beads.closed == []
    assert beads.comments_made == [("bd-1", "[af] blocked: verdict partial: the tests")]


async def test_failed_workflow_blocks_with_one_comment() -> None:
    for status in ("FAILED", "TIMED_OUT", "TERMINATED", "CANCELED"):
        beads = FakeBeads(states=[_running("bd-1", marker("bead-bd-1-1"))])
        flows = FakeFlows(statuses={"bead-bd-1-1": status})
        summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
        assert summary.blocked == ["bd-1"]
        assert beads.blocked == ["bd-1"]
        assert beads.comments_made == [
            ("bd-1", f"[af] blocked: workflow bead-bd-1-1 ended {status}")
        ]


async def test_running_workflow_left_alone_without_comments() -> None:
    beads = FakeBeads(states=[_running("bd-1", marker("bead-bd-1-1"))])
    flows = FakeFlows(statuses={"bead-bd-1-1": "RUNNING"})
    for _ in range(3):
        summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
        assert summary.skipped == {}
    assert beads.comments_made == []


async def test_failed_block_leaves_no_comment() -> None:
    class Unblockable(FakeBeads):
        def block(self, bead_id: str) -> None:
            raise BeadsError("bd update failed")

    beads = Unblockable(states=[_running("bd-1", marker("bead-bd-1-1"))])
    flows = FakeFlows(statuses={"bead-bd-1-1": "FAILED"})
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.blocked == []
    assert "block bd-1 failed" in summary.errors[0]
    assert beads.comments_made == []


async def test_retried_bead_runs_under_a_new_workflow_id() -> None:
    history = [marker("bead-bd-1-1"), "[af] blocked: workflow bead-bd-1-1 ended FAILED"]
    beads = FakeBeads(ready=[_bead("bd-1")], comments={"bd-1": [*history, retried("flaky")]})
    flows = FakeFlows(statuses={"bead-bd-1-1": "FAILED"})
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.spawned == ["bd-1"]
    assert flows.spawned == [("bead-bd-1-2", None)]
    assert ("bd-1", marker("bead-bd-1-2")) in beads.comments_made


async def test_reconcile_reads_the_latest_marker() -> None:
    state = _running("bd-1", marker("bead-bd-1-1"), retried(""), marker("bead-bd-1-2"))
    beads = FakeBeads(states=[state])
    flows = FakeFlows(
        statuses={"bead-bd-1-1": "FAILED", "bead-bd-1-2": "COMPLETED"},
        outcomes={"bead-bd-1-2": _outcome(Verdict.DONE)},
    )
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.closed == ["bd-1"]


async def test_lost_marker_is_written_from_the_running_workflow() -> None:
    beads = FakeBeads(states=[_running("bd-1")])
    flows = FakeFlows(statuses={"bead-bd-1-1": "RUNNING"})
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.reopened == []
    assert beads.comments_made == [("bd-1", marker("bead-bd-1-1"))]


async def test_old_markerless_bead_reopened() -> None:
    beads = FakeBeads(
        states=[BeadState(id="bd-1", updated_at="2026-10-01T10:00:00+00:00", comments=[])]
    )
    flows = FakeFlows()
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.reopened == ["bd-1"]
    assert beads.reopened == ["bd-1"]


async def test_young_markerless_bead_untouched() -> None:
    beads = FakeBeads(
        states=[BeadState(id="bd-1", updated_at="2026-10-02T11:59:00+00:00", comments=[])]
    )
    flows = FakeFlows()
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.reopened == []


async def test_marker_without_workflow_is_skipped() -> None:
    beads = FakeBeads(states=[_running("bd-1", "[af] workflow bead-gone")])
    flows = FakeFlows()
    summary = await poll_once(beads, flows, PROVIDERS, 10, 600, NOW)
    assert summary.closed == []
    assert "no such workflow" in summary.skipped["bd-1"]
