from typing import Any

from temporal_agentic_factory.watchers.beads.mapping import decide, workflow_id
from temporal_agentic_factory.watchers.beads.models import Bead

PROVIDERS = ["claude", "opencode"]
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


def _bead(description: str = "It fails on retries.", **job_fields: Any) -> Bead:
    return Bead(
        id="af-1",
        title="Fix the flaky test",
        description=description,
        job_fields={"provider": "opencode", "workdir": "/tmp"} | job_fields,
    )


def test_bead_becomes_a_job() -> None:
    decision = decide(_bead(), PROVIDERS)
    assert decision.skip == ""
    assert decision.job is not None
    assert decision.job.name == "af-1"
    assert decision.job.prompt == "Fix the flaky test\n\nIt fails on retries."
    assert decision.job.workdir == "/tmp"
    assert decision.job.provider == "opencode"
    assert decision.job.model != ""  # harness default filled, so the UI shows it
    assert decision.output_schema is None


def test_every_af_job_field_reaches_the_job() -> None:
    bead = _bead(
        provider="claude",
        model="sonnet",
        name="flaky",
        tools=["Read", "Edit"],
        timeout_sec=60,
        stall_sec=30,
        context_limit_tokens=1000,
    )
    job = decide(bead, PROVIDERS).job
    assert job is not None
    assert (job.provider, job.model, job.name) == ("claude", "sonnet", "flaky")
    assert job.tools == ["Read", "Edit"]
    assert (job.timeout_sec, job.stall_sec, job.context_limit_tokens) == (60, 30, 1000)


def test_structured_output_asks_for_the_structured_workflow() -> None:
    decision = decide(_bead(structured_output=SCHEMA), PROVIDERS)
    assert decision.job is not None
    assert decision.output_schema == SCHEMA


def test_front_matter_sits_between_defaults_and_af_job() -> None:
    description = "---\nmodel: from-front\nname: front-name\ntimeout_sec: 90\n---\nThe body."
    decision = decide(_bead(description, model="from-meta"), PROVIDERS)
    assert decision.job is not None
    assert decision.job.model == "from-meta"  # af_job wins
    assert decision.job.name == "front-name"  # front matter over the bead-id default
    assert decision.job.timeout_sec == 90
    assert decision.job.prompt == "Fix the flaky test\n\nThe body."  # block stripped


def test_front_matter_alone_routes_a_bead() -> None:
    bead = Bead(id="af-1", title="T", description="---\nprovider: claude\nworkdir: /tmp\n---\nBody")
    decision = decide(bead, PROVIDERS)
    assert decision.job is not None
    assert decision.job.provider == "claude"


def test_unknown_af_job_key_is_left_alone() -> None:
    decision = decide(_bead(colour="blue"), PROVIDERS)
    assert decision.job is None
    assert "af_job" in decision.skip
    assert "colour" in decision.skip


def test_invalid_af_job_value_is_left_alone() -> None:
    decision = decide(_bead(timeout_sec="soon"), PROVIDERS)
    assert decision.job is None
    assert "timeout_sec" in decision.skip


def test_af_job_that_is_not_an_object_is_left_alone() -> None:
    decision = decide(Bead(id="af-1", title="T", job_fields="nope"), PROVIDERS)
    assert "not an object" in decision.skip


def test_unknown_front_matter_key_is_left_alone() -> None:
    decision = decide(_bead("---\nprompt: sneaky\n---\nBody"), PROVIDERS)
    assert decision.job is None
    assert "front matter" in decision.skip


def test_unconfigured_provider_is_left_alone() -> None:
    decision = decide(_bead(provider="claude"), ["opencode"])
    assert decision.job is None
    assert "[providers.claude]" in decision.skip


def test_bead_without_workdir_is_left_alone() -> None:
    decision = decide(Bead(id="af-1", title="T", job_fields={"provider": "claude"}), PROVIDERS)
    assert decision.job is None
    assert "no workdir" in decision.skip


def test_missing_workdir_is_left_alone() -> None:
    decision = decide(_bead(workdir="/no/such/dir"), PROVIDERS)
    assert decision.job is None
    assert "workdir not a directory" in decision.skip


def test_empty_prompt_is_left_alone() -> None:
    decision = decide(Bead(id="af-1", job_fields={"workdir": "/tmp"}), PROVIDERS)
    assert decision.job is None
    assert "empty" in decision.skip


def test_workflow_id_names_the_attempt() -> None:
    assert workflow_id("af-1", 1) == "bead-af-1-1"
    assert workflow_id("af-1", 2) == "bead-af-1-2"
