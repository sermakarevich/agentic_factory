from typing import Any

from factory_store.store import Store
from pydantic import BaseModel
from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job.outputs import extract as outputs
from agentic_factory.job.outputs.contract import Schema
from agentic_factory.settings.load import settings
from agentic_factory.step.providers.catalog import client_for
from temporal_agentic_factory.activities.failure import to_application_error


class OutputsRequest(BaseModel):
    """What the extraction needs: the session to read, and the shape of the
    outputs the job was asked to state."""

    session_id: str
    outputs_schema: Schema


class OutputsActivity:
    def __init__(self, store: Store) -> None:
        self.store = store

    @activity.defn
    async def extract_outputs(self, request: OutputsRequest) -> dict[str, Any]:
        """The app's extraction over the session's stored events, with the
        step client of `settings.step.provider`. A failure keeps its type;
        `OutputsNotStated` is final, so Temporal does not try again."""
        client = client_for(settings.step.provider)
        try:
            return await outputs.extract_outputs(
                self.store, request.session_id, request.outputs_schema, client
            )
        except JobFailed as failure:
            raise to_application_error(failure) from failure
