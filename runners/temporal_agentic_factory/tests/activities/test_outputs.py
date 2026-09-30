import pytest
from factory_store.store import Store
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.failure import OutputsNotStated
from agentic_factory.job.outputs.contract import Schema
from agentic_factory.step.providers.client import Client
from temporal_agentic_factory.activities import outputs as activity
from tests.fakes import FakeStore

SCHEMA: Schema = {"type": "object", "properties": {"urls": {"type": "array"}}}
REQUEST = activity.OutputsRequest(session_id="s1", outputs_schema=SCHEMA)


@pytest.fixture
def db() -> FakeStore:
    return FakeStore()


def extract_outputs(db: FakeStore) -> activity.OutputsActivity:
    return activity.OutputsActivity(db)  # type: ignore[arg-type]


async def test_the_app_extracts_with_the_store_the_schema_and_a_step_client(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[tuple[Store, str, Schema, Client]] = []

    async def fake_extract(
        store: Store, session_id: str, schema: Schema, client: Client
    ) -> dict[str, list[str]]:
        given.append((store, session_id, schema, client))
        return {"urls": ["u"]}

    monkeypatch.setattr(activity.outputs, "extract_outputs", fake_extract)
    found = await ActivityEnvironment().run(extract_outputs(db).extract_outputs, REQUEST)

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
        raise OutputsNotStated("the coder did not state: urls")

    monkeypatch.setattr(activity.outputs, "extract_outputs", fake_extract)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(extract_outputs(db).extract_outputs, REQUEST)
    assert err.value.type == "OutputsNotStated" and err.value.non_retryable
