"""The task queue a provider's coder runs wait in: only `af coders` polls it,
with that provider's limit."""

from temporal_agentic_factory.settings.load import settings


def coder_queue(provider: str) -> str:
    """`<[temporal] task_queue>-coder-<provider>`: `agentic-factory-coder-claude`."""
    return f"{settings.temporal.task_queue}-coder-{provider}"
