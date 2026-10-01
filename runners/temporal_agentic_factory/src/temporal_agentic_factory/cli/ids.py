"""Workflow id helpers shared by every `af` submit command."""

from uuid import uuid4

from temporal_agentic_factory.settings.load import settings


def new_id(prefix: str, workflow_id: str | None = None) -> str:
    """The id to start a workflow with: the given one, or `prefix-<uuid>`.

    A caller-provided id makes the start idempotent: re-running the same
    submit reuses the workflow instead of starting a duplicate.
    """
    if workflow_id:
        return workflow_id
    return f"{prefix}-{uuid4().hex[: settings.cli.job_id_chars]}"
