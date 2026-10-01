"""Bead to job: which beads the puller takes, and what job each becomes.

Only beads whose coder maps to a known harness are taken; anything else is
left for fleet workers, with the reason recorded in the tick summary.
"""

from pathlib import Path

from pydantic import BaseModel

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from temporal_agentic_factory.beads.models import Bead

PROVIDERS = {"claude": "claude", "opencode": "opencode"}


class BeadDecision(BaseModel):
    """One bead judged: the job to spawn, or the reason it is left alone."""

    bead_id: str
    job: Job | None = None
    skip: str = ""


def decide(bead: Bead) -> BeadDecision:
    """The job for a bead, or the skip with its reason."""
    provider = PROVIDERS.get(bead.coder.strip().lower())
    if provider is None:
        return BeadDecision(bead_id=bead.id, skip=f"no harness for coder {bead.coder!r}")
    if not bead.cwd or not Path(bead.cwd).is_dir():
        return BeadDecision(bead_id=bead.id, skip=f"workdir not a directory: {bead.cwd!r}")
    prompt = f"{bead.title}\n\n{bead.description}".strip()
    if not prompt:
        return BeadDecision(bead_id=bead.id, skip="empty title and description")
    job = Job(
        name=bead.id,
        prompt=prompt,
        workdir=bead.cwd,
        provider=provider,
        model=bead.model,
    )
    return BeadDecision(
        bead_id=bead.id,
        job=with_default_model(job, harness_for(provider)),  # so the UI shows the model
    )


def workflow_id(bead_id: str) -> str:
    """The id a bead's job workflow starts with: repeats are idempotent."""
    return f"bead-{bead_id}"
