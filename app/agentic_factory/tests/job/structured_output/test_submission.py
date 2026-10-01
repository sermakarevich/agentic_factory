from collections.abc import AsyncIterator

import pytest
from factory_store.store import Store

from agentic_factory.job.structured_output.contract import Schema, Source
from agentic_factory.job.structured_output.submission import (
    NoSchemaSaved,
    submit,
    submitted_output,
)

SCHEMA: Schema = {
    "type": "object",
    "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
    "required": ["urls"],
}


@pytest.fixture
async def store() -> AsyncIterator[Store]:
    store = Store.from_url("sqlite+aiosqlite:///:memory:")
    await store.create_all()
    await store.start_session("s1", "claude", "m", "/w", "fetch")
    await store.save_output_schema("s1", SCHEMA)
    yield store
    await store.dispose()


async def test_a_valid_submission_is_saved_as_submitted(store: Store) -> None:
    checked = await submit(store, "s1", '{"urls": ["u"]}')
    assert checked.errors == []
    row = await store.load_structured_output("s1")
    assert row is not None and row.source == Source.SUBMITTED and row.schema == SCHEMA
    assert await submitted_output(store, "s1") == {"urls": ["u"]}


async def test_an_invalid_submission_saves_nothing(store: Store) -> None:
    checked = await submit(store, "s1", '{"urls": [1]}')
    assert checked.errors == ["urls[0]: 1 is not of type 'string'"]
    assert await store.load_structured_output("s1") is None
    assert await submitted_output(store, "s1") is None


async def test_a_later_valid_submission_replaces_the_earlier_one(store: Store) -> None:
    await submit(store, "s1", '{"urls": ["a"]}')
    await submit(store, "s1", '{"urls": [2]}')
    await submit(store, "s1", '{"urls": ["b"]}')
    assert await submitted_output(store, "s1") == {"urls": ["b"]}


async def test_a_session_with_no_schema_is_refused(store: Store) -> None:
    with pytest.raises(NoSchemaSaved):
        await submit(store, "nobody", "{}")


async def test_an_output_picked_out_by_the_step_is_not_a_submission(store: Store) -> None:
    await store.save_structured_output("s1", SCHEMA, {"urls": []}, Source.LAST_MESSAGE)
    assert await submitted_output(store, "s1") is None
