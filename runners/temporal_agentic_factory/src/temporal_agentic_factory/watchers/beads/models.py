"""Bead shapes: what `bd ready --json` reports with its af metadata, and what a tick tracks."""

from pydantic import BaseModel, Field


class Bead(BaseModel):
    """One startable bead with the routing context a spawn needs.

    All strings, "" when unset. `provider`, `cwd` and `model` come from the
    bead's metadata; an empty model means the provider's default.
    """

    id: str
    title: str = ""
    description: str = ""
    provider: str = ""
    model: str = ""
    cwd: str = ""


class BeadState(BaseModel):
    """One in_progress bead as a tick sees it: its id, last update, and comments."""

    id: str
    updated_at: str = ""
    comments: list[str] = Field(default_factory=list)


class PollSummary(BaseModel):
    """What one tick did: spawned and closed bead ids, skips with reasons, errors."""

    spawned: list[str] = Field(default_factory=list)
    closed: list[str] = Field(default_factory=list)
    reopened: list[str] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
