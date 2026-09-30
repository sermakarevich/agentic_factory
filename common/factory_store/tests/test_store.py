from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from factory_store import schema
from factory_store.schema import Outcome
from factory_store.store import JobRecord, Store, Totals


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


async def test_starting_a_later_try_abandons_one_left_running() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        await store.start_try("s1", 1)
        await store.start_try("s1", 2)
        async with store.engine.connect() as conn:
            result = await conn.execute(
                select(schema.attempt)
                .where(schema.attempt.c.session_id == "s1")
                .order_by(schema.attempt.c.attempt)
            )
            first, second = result.mappings().all()
        assert first["outcome"] == "failed"
        assert first["failure"].startswith("abandoned")
        assert first["ended_at"] is not None
        assert second["outcome"] == "running"
    finally:
        await store.dispose()


async def test_a_finished_try_keeps_its_totals_and_result() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        await store.start_try("s1", 1)
        totals = Totals(input_tokens=10, output_tokens=5, cost_usd=0.25, duration_sec=1.5, turns=2)
        await store.finish_try("s1", 1, Outcome.DONE, totals=totals, result={"ok": True})
        await store.start_try("s1", 2)
        await store.finish_try("s1", 2, Outcome.FAILED, "Stalled: quiet", Totals(turns=1))
        first, second = await store.load_tries("s1")
        assert first.totals == totals and first.result == {"ok": True}
        assert first.outcome == "done" and first.ended_at is not None
        assert second.totals == Totals(turns=1) and second.result == {}
        assert second.failure == "Stalled: quiet"
        assert first.totals + second.totals == Totals(
            input_tokens=10, output_tokens=5, cost_usd=0.25, duration_sec=1.5, turns=3
        )
    finally:
        await store.dispose()


async def test_a_restarted_try_forgets_its_totals() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        await store.start_try("s1", 1)
        await store.finish_try("s1", 1, Outcome.DONE, totals=Totals(turns=3), result={"ok": True})
        await store.start_try("s1", 1)
        (row,) = await store.load_tries("s1")
        assert row.totals == Totals() and row.result == {}
    finally:
        await store.dispose()


async def test_the_job_row_is_replaced_not_duplicated() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        at = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
        record = JobRecord(
            started_at=at,
            ended_at=at,
            tries=2,
            outcome=Outcome.DONE,
            failure="",
            totals=Totals(cost_usd=0.5),
            result={"ok": True},
            verdict="done",
        )
        await store.save_job("s1", record)
        await store.save_job("s1", replace(record, tries=3, verdict="partial"))
        async with store.engine.connect() as conn:
            result = await conn.execute(select(schema.job).where(schema.job.c.session_id == "s1"))
            rows = result.mappings().all()
        assert len(rows) == 1
        assert rows[0]["tries"] == 3 and rows[0]["verdict"] == "partial"
        assert rows[0]["outcome"] == "done" and rows[0]["cost_usd"] == 0.5
        assert dict(rows[0]["result"]) == {"ok": True}
    finally:
        await store.dispose()


async def test_event_payload_with_nul_comes_back_escaped() -> None:
    store = await make_store()
    try:
        await store.start_session("s1", "opencode", "m", "/w", "do it")
        at = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
        payload: dict[str, Any] = {"msg": "a\x00b", "items": ["x\x00y", 1]}
        await store.append_event("s1", 1, at, "progress", payload)
        (event,) = await store.load_events("s1")
        assert event.payload == {"msg": "a\\u0000b", "items": ["x\\u0000y", 1]}
        assert "\x00" not in str(event.payload)
    finally:
        await store.dispose()
