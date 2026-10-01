"""The submit commands' admission check against the global job cap."""

from temporal_agentic_factory.capacity import free_slots
from temporal_agentic_factory.cli.errors import fail, run_coro
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings


def refuse_when_full() -> None:
    """Exit with a clean error when no `[limits] max_concurrent_jobs` slot is free."""
    if run_coro(_free_slots()) == 0:
        fail(
            f"all {settings.limits.max_concurrent_jobs} job slots are taken"
            " ([limits] max_concurrent_jobs); retry later, raise it, or pass --force"
        )


async def _free_slots() -> int | None:
    return await free_slots(
        await connect(), settings.limits.max_concurrent_jobs, settings.temporal.task_queue
    )
