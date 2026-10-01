"""The workflow id every `af` submit command starts with."""

import re
from uuid import uuid4

from temporal_agentic_factory.settings.load import settings


def new_id(prefix: str, name: str, workflow_id: str | None = None) -> str:
    """The id to start a workflow with: the given one, or one read from the
    name: `job-fix-login-4f2a`, `distill-arxiv-org-2401-12345-9c1e`, and
    `job-4f2a-9c1e` when there is no name.

    A caller-provided id makes the start idempotent: re-running the same
    submit reuses the workflow instead of starting a duplicate.
    """
    if workflow_id:
        return workflow_id
    suffix = uuid4().hex[: settings.cli.id_suffix_chars]
    middle = _slug(name) or uuid4().hex[: settings.cli.id_suffix_chars]
    return f"{prefix}-{middle}-{suffix}"


def _slug(name: str) -> str:
    """`Agent Memory/Tech` -> `agent-memory-tech`, cut to `[cli] slug_chars`."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[: settings.cli.slug_chars].rstrip("-")
