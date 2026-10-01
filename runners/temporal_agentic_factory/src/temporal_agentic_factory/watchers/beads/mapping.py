"""Bead to job: which beads the puller takes, and what job each becomes.

Only beads whose metadata names a configured provider and a workdir are taken;
anything else is left open, with the reason recorded in the tick summary.
"""

from collections.abc import Collection
from pathlib import Path

from pydantic import BaseModel

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from temporal_agentic_factory.watchers.beads.models import Bead


class BeadDecision(BaseModel):
    """One bead judged: the job to spawn, or the reason it is left alone."""

    bead_id: str
    job: Job | None = None
    skip: str = ""


def decide(bead: Bead, providers: Collection[str]) -> BeadDecision:
    """The job for a bead, or the skip with its reason. `providers` are the
    configured ones: a bead for any other would wait in a queue nobody polls."""
    provider = bead.provider.strip().lower()
    if not provider:
        return BeadDecision(bead_id=bead.id, skip="no provider in the bead's metadata")
    if provider not in providers:
        return BeadDecision(
            bead_id=bead.id, skip=f"provider {provider!r} has no [providers.{provider}] table"
        )
    if not bead.cwd:
        return BeadDecision(bead_id=bead.id, skip="no workdir in the bead's metadata")
    if not Path(bead.cwd).is_dir():
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
