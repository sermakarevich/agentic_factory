"""The submission activities on an in-memory sqlite store."""

from collections.abc import AsyncIterator

import pytest
from factory_store.store import Store
from temporalio.testing import ActivityEnvironment

from agentic_factory.job.contract import Job
from agentic_factory.job.structured_output.contract import Schema
from agentic_factory.job.structured_output.submission import submit
from temporal_agentic_factory.workflows.structured_output import submission as activity

SCHEMA: Schema = {"type": "object", "properties": {"urls": {"type": "array"}}}


@pytest.fixture
async def store() -> AsyncIterator[Store]:
    store = Store.from_url("sqlite+aiosqlite:///:memory:")
    await store.create_all()
    await store.start_session("s1", "claude", "m", "/w", "fetch")
    yield store
    await store.dispose()


async def test_asking_saves_the_schema_and_names_the_command(store: Store) -> None:
    job = Job(name="urls", prompt="fetch", workdir=".", model="m", session_id="s1")
    request = activity.SubmissionRequest(job=job, output_schema=SCHEMA)

    asked = await ActivityEnvironment().run(
        activity.SubmissionActivity(store).ask_for_submission, request
    )

    assert await store.load_output_schema("s1") == SCHEMA
    assert asked.command.endswith(" output submit s1") and asked.command in asked.job.prompt


async def test_reading_gives_the_submission_or_none(store: Store) -> None:
    read = activity.SubmissionActivity(store).read_submitted_output
    await store.save_output_schema("s1", SCHEMA)
    assert await ActivityEnvironment().run(read, "s1") is None

    await submit(store, "s1", '{"urls": ["u"]}')
    assert await ActivityEnvironment().run(read, "s1") == {"urls": ["u"]}


def test_af_is_the_script_beside_the_python_when_it_is_there() -> None:
    assert activity.af_path().endswith("af")
