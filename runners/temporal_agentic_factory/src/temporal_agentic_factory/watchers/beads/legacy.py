"""The Temporal Schedule the watcher replaced: removed by `af beads start`."""

from temporalio.client import Client, ScheduleHandle
from temporalio.service import RPCError, RPCStatusCode

LEGACY_SCHEDULE_ID = "beads-poll"


async def deleted_legacy_schedule(client: Client) -> bool:
    """The old `beads-poll` schedule deleted; False when there was none."""
    return await delete_schedule(client.get_schedule_handle(LEGACY_SCHEDULE_ID))


async def delete_schedule(handle: ScheduleHandle) -> bool:
    """Delete the schedule; False when it does not exist, so there was nothing to delete.

    The server's NOT_FOUND message varies ("workflow execution already
    completed"), so the status code decides, not the text.
    """
    try:
        await handle.delete()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return False
    return True
