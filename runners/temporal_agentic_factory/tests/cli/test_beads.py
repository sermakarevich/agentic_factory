from typing import cast

import pytest
from temporalio.client import ScheduleHandle
from temporalio.service import RPCError, RPCStatusCode

from temporal_agentic_factory.cli.beads import delete_schedule


class FakeHandle:
    """A schedule handle whose delete fails with the given error, or succeeds."""

    def __init__(self, error: RPCError | None) -> None:
        self.error = error
        self.deleted = False

    async def delete(self) -> None:
        if self.error is not None:
            raise self.error
        self.deleted = True


async def test_delete_schedule_deletes_an_existing_one() -> None:
    handle = FakeHandle(None)
    await delete_schedule(cast(ScheduleHandle, handle))
    assert handle.deleted


async def test_delete_schedule_treats_not_found_as_nothing_to_delete() -> None:
    error = RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b"")
    await delete_schedule(cast(ScheduleHandle, FakeHandle(error)))


async def test_delete_schedule_raises_other_failures() -> None:
    error = RPCError("schedule not found, they say", RPCStatusCode.UNAVAILABLE, b"")
    with pytest.raises(RPCError):
        await delete_schedule(cast(ScheduleHandle, FakeHandle(error)))
