from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from factory_store import schema
from factory_store.schema import Outcome
from factory_store.store import Store


async def make_store() -> Store:
    store = Store.from_url("sqlite+aiosqlite:///:memory:")
    await store.create_all()
    return store


async def test_session_and_try_round_trip() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        await store.start_try("s1", 1)
        await store.finish_try("s1", 1, Outcome.DONE)
        async with store.engine.connect() as conn:
            result = await conn.execute(
                select(schema.attempt).where(schema.attempt.c.session_id == "s1")
            )
            rows = result.mappings().all()
        assert len(rows) == 1
        assert rows[0]["outcome"] == "done"
        assert rows[0]["ended_at"] is not None
        assert rows[0]["failure"] == ""
    finally:
        await store.dispose()


async def test_start_try_twice_resets_the_row() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        await store.start_try("s1", 2)
        await store.finish_try("s1", 2, Outcome.FAILED, "boom")
        await store.start_try("s1", 2)
        async with store.engine.connect() as conn:
            result = await conn.execute(
                select(schema.attempt)
                .where(schema.attempt.c.session_id == "s1")
                .where(schema.attempt.c.attempt == 2)
            )
            rows = result.mappings().all()
        assert len(rows) == 1
        assert rows[0]["outcome"] == "running"
        assert rows[0]["failure"] == ""
        assert rows[0]["ended_at"] is None
    finally:
        await store.dispose()


async def test_events_come_back_in_insert_order_across_tries() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        t1 = datetime(2026, 9, 30, 12, 0, 1, tzinfo=UTC)
        t2 = datetime(2026, 9, 30, 12, 0, 2, tzinfo=UTC)
        t3 = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
        p1: dict[str, Any] = {"items": [1, 2, {"n": 3}], "msg": "first"}
        p2: dict[str, Any] = {"items": [], "msg": "second"}
        p3: dict[str, Any] = {"items": [True], "msg": "third"}
        id1 = await store.append_event("s1", 1, t1, "start", p1)
        id2 = await store.append_event("s1", 1, t2, "progress", p2)
        id3 = await store.append_event("s1", 2, t3, "retry", p3)
        assert [id1, id2, id3] == sorted([id1, id2, id3])
        events = await store.load_events("s1")
        assert [e.id for e in events] == [id1, id2, id3]
        assert [e.attempt for e in events] == [1, 1, 2]
        assert [e.payload for e in events] == [p1, p2, p3]
        assert [e.at for e in events] == [t1, t2, t3]
        assert all(e.at.tzinfo is not None for e in events)
    finally:
        await store.dispose()


async def test_conversation_and_report_replace_earlier_rows() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        await store.save_conversation("s1", "first", 1)
        await store.save_conversation("s1", "second", 2)
        async with store.engine.connect() as conn:
            result = await conn.execute(
                select(schema.conversation).where(schema.conversation.c.session_id == "s1")
            )
            conv_rows = result.mappings().all()
        assert len(conv_rows) == 1
        assert conv_rows[0]["text"] == "second"

        result_dict: dict[str, Any] = {"ok": True, "files": ["a.py"]}
        summary_dict: dict[str, Any] = {"points": [1, 2]}
        await store.save_report("s1", {"ok": False}, {"points": []}, "bad")
        await store.save_report("s1", result_dict, summary_dict, "good")
        async with store.engine.connect() as conn:
            result = await conn.execute(
                select(schema.report).where(schema.report.c.session_id == "s1")
            )
            report_rows = result.mappings().all()
        assert len(report_rows) == 1
        assert report_rows[0]["verdict"] == "good"
        assert dict(report_rows[0]["result"]) == result_dict
        assert dict(report_rows[0]["summary"]) == summary_dict
    finally:
        await store.dispose()
