from temporal_agentic_factory.watchers.beads.mapping import decide, workflow_id
from temporal_agentic_factory.watchers.beads.models import Bead

PROVIDERS = ["claude", "opencode"]


def _bead(**overrides):  # type: ignore[no-untyped-def]
    base = {
        "id": "af-1",
        "title": "Fix the flaky test",
        "description": "It fails on retries.",
        "provider": "opencode",
        "model": "",
        "cwd": "/tmp",
    }
    return Bead(**(base | overrides))


def test_mapped_bead_becomes_a_job() -> None:
    decision = decide(_bead(), PROVIDERS)
    assert decision.skip == ""
    assert decision.job is not None
    assert decision.job.name == "af-1"
    assert "Fix the flaky test" in decision.job.prompt
    assert decision.job.workdir == "/tmp"
    assert decision.job.provider == "opencode"
    assert decision.job.model != ""  # harness default filled, so the UI shows it


def test_bead_model_kept_when_given() -> None:
    decision = decide(_bead(provider="claude", model="sonnet"), PROVIDERS)
    assert decision.job is not None
    assert decision.job.provider == "claude"
    assert decision.job.model == "sonnet"


def test_bead_without_provider_is_left_alone() -> None:
    decision = decide(_bead(provider=""), PROVIDERS)
    assert decision.job is None
    assert "no provider" in decision.skip


def test_unconfigured_provider_is_left_alone() -> None:
    decision = decide(_bead(provider="claude"), ["opencode"])
    assert decision.job is None
    assert "[providers.claude]" in decision.skip


def test_bead_without_cwd_is_left_alone() -> None:
    decision = decide(_bead(cwd=""), PROVIDERS)
    assert decision.job is None
    assert "no workdir" in decision.skip


def test_missing_workdir_is_left_alone() -> None:
    decision = decide(_bead(cwd="/no/such/dir"), PROVIDERS)
    assert decision.job is None
    assert "workdir not a directory" in decision.skip


def test_empty_prompt_is_left_alone() -> None:
    decision = decide(_bead(title="", description="  "), PROVIDERS)
    assert decision.job is None
    assert "empty" in decision.skip


def test_workflow_id_is_prefixed() -> None:
    assert workflow_id("af-1") == "bead-af-1"
