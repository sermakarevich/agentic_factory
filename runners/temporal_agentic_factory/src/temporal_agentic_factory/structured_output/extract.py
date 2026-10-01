from typing import Any

from factory_store.store import Store
from pydantic import BaseModel
from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job.structured_output import extract as structured_output
from agentic_factory.job.structured_output.contract import Schema
from agentic_factory.settings.load import settings
from agentic_factory.step.providers.catalog import client_for
from temporal_agentic_factory.failure import to_application_error


class StructuredOutputRequest(BaseModel):
    """What the extraction needs: the session to read, and the shape of the
    structured output the job was asked to state."""

    session_id: str
    output_schema: Schema


class StructuredOutputActivity:
    def __init__(self, store: Store) -> None:
        self.store = store

    @activity.defn
    async def extract_structured_output(self, request: StructuredOutputRequest) -> dict[str, Any]:
        """The app's extraction over the session's stored events, with the
        step client of `settings.step.provider`. A failure keeps its type;
        `StructuredOutputNotStated` is final, so Temporal does not try again."""
        client = client_for(settings.step.provider)
        try:
            return await structured_output.extract_structured_output(
                self.store, request.session_id, request.output_schema, client
            )
        except JobFailed as failure:
            raise to_application_error(failure) from failure
