import logging
from typing import Any

from factory_store.store import Store, StoredEvent

from agentic_factory.event import EventKind
from agentic_factory.failure import OutputsNotStated
from agentic_factory.job.outputs.contract import Extraction, Schema, Source, field_names
from agentic_factory.job.outputs.step import extract
from agentic_factory.job.report.conversation import render
from agentic_factory.step.providers.client import Client

log = logging.getLogger("agentic_factory.job")


async def extract_outputs(
    store: Store, session_id: str, schema: Schema, client: Client
) -> dict[str, Any]:
    """After the job: the outputs the coder stated, picked out by a step and
    saved with the schema and where they were found. First from the coder's
    last message, where the prompt asked for them; when that says not
    stated, from the whole conversation. Raises `OutputsNotStated` when
    neither states them, and the step's `JobFailed` when the model could
    not answer; no row is written then."""
    rows = await store.load_events(session_id)
    source = Source.LAST_MESSAGE
    found = await _from_last_message(rows, schema, client)
    if found.outputs is None:
        log.info("outputs not in the last message; reading the conversation")
        source = Source.CONVERSATION
        found = await _from_conversation(store, session_id, rows, schema, client)
    if found.outputs is None:
        raise OutputsNotStated(f"the coder did not state: {', '.join(found.missing)}")
    await store.save_outputs(session_id, schema, found.outputs, source)
    return found.outputs


def last_message(rows: list[StoredEvent]) -> str:
    """The text of the coder's last `ai` event that has any, over every try."""
    for row in reversed(rows):
        if row.kind == EventKind.AI and row.payload.get("content"):
            return str(row.payload["content"])
    return ""


async def _from_last_message(rows: list[StoredEvent], schema: Schema, client: Client) -> Extraction:
    text = last_message(rows)
    if not text:
        return Extraction(outputs=None, missing=field_names(schema))
    return await extract(text, schema, client)


async def _from_conversation(
    store: Store, session_id: str, rows: list[StoredEvent], schema: Schema, client: Client
) -> Extraction:
    session = await store.load_session(session_id)
    return await extract(render(session.prompt if session else "", rows), schema, client)
