"""Bead shapes: what `fleet ready --json` reports and what a tick tracks."""

from pydantic import BaseModel, Field


class Bead(BaseModel):
    """One startable bead with the routing context a spawn needs.

    All strings, "" when unset: the shape of `fleet ready --json` rows.
    `isolation` is carried but not acted on; the runner has no isolation.
    """

    id: str
    title: str = ""
    description: str = ""
    coder: str = ""
    model: str = ""
    cwd: str = ""
    isolation: str = ""


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
