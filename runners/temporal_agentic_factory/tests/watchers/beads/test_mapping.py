from temporal_agentic_factory.watchers.beads.mapping import decide, workflow_id
from temporal_agentic_factory.watchers.beads.models import Bead


def _bead(**overrides):  # type: ignore[no-untyped-def]
    base = {
        "id": "bd-1",
        "title": "Fix the flaky test",
        "description": "It fails on retries.",
        "coder": "opencode",
        "model": "",
        "cwd": "/tmp",
    }
    return Bead(**(base | overrides))


def test_mapped_bead_becomes_a_job() -> None:
    decision = decide(_bead())
    assert decision.skip == ""
    assert decision.job is not None
    assert decision.job.name == "bd-1"
    assert "Fix the flaky test" in decision.job.prompt
    assert decision.job.workdir == "/tmp"
    assert decision.job.provider == "opencode"
    assert decision.job.model != ""  # harness default filled, so the UI shows it


def test_bead_model_kept_when_given() -> None:
    decision = decide(_bead(coder="claude", model="sonnet"))
    assert decision.job is not None
    assert decision.job.provider == "claude"
    assert decision.job.model == "sonnet"


def test_unknown_coder_is_left_alone() -> None:
    decision = decide(_bead(coder="codex"))
    assert decision.job is None
    assert "codex" in decision.skip


def test_missing_workdir_is_left_alone() -> None:
    decision = decide(_bead(cwd="/no/such/dir"))
    assert decision.job is None
    assert "workdir" in decision.skip


def test_empty_prompt_is_left_alone() -> None:
    decision = decide(_bead(title="", description="  "))
    assert decision.job is None
    assert "empty" in decision.skip


def test_workflow_id_is_prefixed() -> None:
    assert workflow_id("bd-1") == "bead-bd-1"
