from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from factory_store.schema import Outcome, metadata

TABLES = {"session", "attempt", "event", "conversation", "report"}


async def test_every_table_is_created_on_sqlite() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        names = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    await engine.dispose()
    assert names == TABLES


def test_outcome_values() -> None:
    assert {o.value for o in Outcome} == {"running", "done", "failed"}
