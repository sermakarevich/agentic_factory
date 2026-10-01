from typing import Any

import pytest
from temporalio.service import RPCError, RPCStatusCode

from temporal_agentic_factory.watchers.beads import temporal
from temporal_agentic_factory.watchers.beads.poll import UnknownWorkflow
from temporal_agentic_factory.watchers.beads.temporal import TemporalWorkflows


class FakeHandle:
    """A workflow handle whose describe always fails with the given error."""

    def __init__(self, error: RPCError) -> None:
        self.error = error

    async def describe(self) -> None:
        raise self.error


class FakeClient:
    """A client that hands out failing workflow handles."""

    def __init__(self, error: RPCError) -> None:
        self.error = error

    def get_workflow_handle(self, workflow_id: str) -> FakeHandle:
        return FakeHandle(self.error)


def _connect_to(monkeypatch: pytest.MonkeyPatch, error: RPCError) -> None:
    async def fake_connect() -> Any:
        return FakeClient(error)

    monkeypatch.setattr(temporal, "connect", fake_connect)


async def test_status_of_an_absent_workflow_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    error = RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b"")
    _connect_to(monkeypatch, error)
    with pytest.raises(UnknownWorkflow):
        await TemporalWorkflows().status_of("bead-x")


async def test_status_of_raises_other_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    error = RPCError("not found, but really down", RPCStatusCode.UNAVAILABLE, b"")
    _connect_to(monkeypatch, error)
    with pytest.raises(RPCError):
        await TemporalWorkflows().status_of("bead-x")
