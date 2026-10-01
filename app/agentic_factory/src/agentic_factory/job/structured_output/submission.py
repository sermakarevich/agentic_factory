from typing import Any

from factory_store.store import Store

from agentic_factory.job.structured_output.check import Checked, check
from agentic_factory.job.structured_output.contract import Schema, Source


class NoSchemaSaved(Exception):
    """No schema is saved for the session: an unknown session id, or a job
    that was not asked for a structured output."""


async def submit(store: Store, session_id: str, text: str) -> Checked:
    """The coder's JSON checked against the session's saved schema and, when
    it matches, saved as the session's structured output, replacing an
    earlier one. Nothing is saved when it does not match. Raises
    `NoSchemaSaved` when the session has no schema."""
    schema = await saved_schema(store, session_id)
    checked = check(text, schema)
    if checked.structured_output is not None:
        await store.save_structured_output(
            session_id, schema, checked.structured_output, Source.SUBMITTED
        )
    return checked


async def saved_schema(store: Store, session_id: str) -> Schema:
    """The schema the workflow saved for the session before the coder started."""
    schema = await store.load_output_schema(session_id)
    if schema is None:
        raise NoSchemaSaved(f"no structured output schema is saved for session {session_id}")
    return schema


async def submitted_output(store: Store, session_id: str) -> dict[str, Any] | None:
    """The coder's last valid submission, or None when it submitted none."""
    row = await store.load_structured_output(session_id)
    if row is None or row.source != Source.SUBMITTED:
        return None
    return row.structured_output
