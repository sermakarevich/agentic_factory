"""Bead to job: which beads the puller takes, and what job each becomes.

A bead's job parameters come from three places, lowest first: Job's own
defaults (the settings), the front matter at the top of its description, and
its `af_job` metadata. The prompt is the title and the description without
the front matter; the name defaults to the bead id. A bead whose parameters
do not validate, with no workdir or an unconfigured provider, is left open
with the reason.
"""

from collections.abc import Collection
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.structured_output.contract import Schema
from temporal_agentic_factory.watchers.beads.client import JOB_KEY
from temporal_agentic_factory.watchers.beads.front_matter import (
    FrontMatterError,
    split_front_matter,
)
from temporal_agentic_factory.watchers.beads.models import Bead
from temporal_agentic_factory.watchers.beads.parameters import (
    InvalidParameters,
    errors_line,
    parameters_of,
)

SCHEMA_KEY = "structured_output"


class BeadDecision(BaseModel):
    """One bead judged: the job to spawn (with the schema of its structured
    output, if it asks for one), or the reason it is left alone."""

    bead_id: str
    job: Job | None = None
    output_schema: Schema | None = None
    skip: str = ""


class Skip(ValueError):
    """Why a bead cannot become a job."""


def decide(bead: Bead, providers: Collection[str]) -> BeadDecision:
    """The job for a bead, or the skip with its reason. `providers` are the
    configured ones: a bead for any other would wait in a queue nobody polls."""
    try:
        fields, body = _fields_and_body(bead)
        job = _job_of(bead, fields, body, providers)
    except Skip as reason:
        return BeadDecision(bead_id=bead.id, skip=str(reason))
    return BeadDecision(
        bead_id=bead.id,
        job=with_default_model(job, harness_for(job.provider)),  # so the UI shows the model
        output_schema=fields.get(SCHEMA_KEY),
    )


def _fields_and_body(bead: Bead) -> tuple[dict[str, Any], str]:
    """The merged job parameters (front matter, then `af_job` over it) and the
    description without its front matter."""
    try:
        front, body = split_front_matter(bead.description)
        from_front = parameters_of(front, "front matter")
        from_metadata = parameters_of(bead.job_fields or {}, JOB_KEY)
    except (FrontMatterError, InvalidParameters) as error:
        raise Skip(str(error)) from error
    return from_front | from_metadata, body


def _job_of(bead: Bead, fields: dict[str, Any], body: str, providers: Collection[str]) -> Job:
    """The Job the parameters describe, checked against what the runners can run."""
    workdir = _workdir_of(fields)
    prompt = f"{bead.title}\n\n{body}".strip()
    if not prompt:
        raise Skip("empty title and description")
    job_fields = {key: value for key, value in fields.items() if key != SCHEMA_KEY}
    try:
        job = Job(**({"name": bead.id} | job_fields | {"prompt": prompt, "workdir": workdir}))
    except ValidationError as error:
        raise Skip(f"invalid job: {errors_line(error)}") from error
    provider = job.provider.strip().lower()
    if provider not in providers:
        raise Skip(f"provider {provider!r} has no [providers.{provider}] table")
    return job.model_copy(update={"provider": provider})


def _workdir_of(fields: dict[str, Any]) -> str:
    """The job's workdir, `~` expanded: required, absolute and an existing folder."""
    given = str(fields.get("workdir") or "")
    if not given:
        raise Skip("no workdir in the bead's af_job metadata or front matter")
    workdir = Path(given).expanduser()
    if not workdir.is_absolute():
        raise Skip(f"workdir not absolute: {given!r}")
    if not workdir.is_dir():
        raise Skip(f"workdir not a directory: {given!r}")
    return str(workdir)


def workflow_id(bead_id: str, attempt: int) -> str:
    """The id one attempt of a bead's job workflow starts with: repeats of an
    attempt are idempotent, a retry gets a new one."""
    return f"bead-{bead_id}-{attempt}"
