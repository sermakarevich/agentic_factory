"""Bead shapes: what `bd` reports with its af metadata, what `bd create` is told, and what
a tick tracks."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Status(StrEnum):
    """The bead statuses af reads or sets."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    CLOSED = "closed"


class Bead(BaseModel):
    """One bead with what a spawn needs: its text, its status, and its `af_job`
    metadata as stored (None when unset; validated only when it becomes a job)."""

    id: str
    title: str = ""
    description: str = ""
    status: str = ""
    job_fields: Any = None


class BeadOptions(BaseModel):
    """What `bd create` is told beside the text: the beads this one depends on
    (set in the same call, so it is never ready before them), its parent,
    labels, type and an explicit id. Empty = bd's own."""

    after: list[str] = Field(default_factory=list)
    parent: str = ""
    labels: list[str] = Field(default_factory=list)
    type: str = ""
    id: str = ""


class BeadState(BaseModel):
    """One in_progress bead as a tick sees it: its id, last update, and comments."""

    id: str
    updated_at: str = ""
    comments: list[str] = Field(default_factory=list)


class PollSummary(BaseModel):
    """What one tick did: spawned, closed and blocked bead ids, skips with reasons, errors."""

    spawned: list[str] = Field(default_factory=list)
    closed: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)
    reopened: list[str] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
