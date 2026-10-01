import pytest
from factory_store.store import Store
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.failure import StructuredOutputNotStated
from agentic_factory.job.structured_output.contract import Schema
from agentic_factory.step.providers.client import Client
from temporal_agentic_factory.workflows.structured_output import extract as activity
from tests.fakes import FakeStore

SCHEMA: Schema = {"type": "object", "properties": {"urls": {"type": "array"}}}
REQUEST = activity.StructuredOutputRequest(session_id="s1", output_schema=SCHEMA)


@pytest.fixture
def db() -> FakeStore:
    return FakeStore()


def extract_structured_output(db: FakeStore) -> activity.StructuredOutputActivity:
    return activity.StructuredOutputActivity(db)  # type: ignore[arg-type]


async def test_the_app_extracts_with_the_store_the_schema_and_a_step_client(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[tuple[Store, str, Schema, Client]] = []

    async def fake_extract(
        store: Store, session_id: str, schema: Schema, client: Client
    ) -> dict[str, list[str]]:
        given.append((store, session_id, schema, client))
        return {"urls": ["u"]}

    monkeypatch.setattr(activity.structured_output, "extract_structured_output", fake_extract)
    found = await ActivityEnvironment().run(
        extract_structured_output(db).extract_structured_output, REQUEST
    )

    assert found == {"urls": ["u"]}
    ((store, session_id, schema, client),) = given
    assert store is db and (session_id, schema) == ("s1", SCHEMA)
    assert isinstance(client, Client)


async def test_not_stated_becomes_a_final_typed_error(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_extract(
        store: Store, session_id: str, schema: Schema, client: Client
    ) -> dict[str, list[str]]:
        raise StructuredOutputNotStated("the coder did not state: urls")

    monkeypatch.setattr(activity.structured_output, "extract_structured_output", fake_extract)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(
            extract_structured_output(db).extract_structured_output, REQUEST
        )
    assert err.value.type == "StructuredOutputNotStated" and err.value.non_retryable
