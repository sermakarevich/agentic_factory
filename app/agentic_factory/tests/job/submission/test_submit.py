import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from factory_store.store import Store

from agentic_factory.job.report.contract import Verdict
from agentic_factory.job.submission.contract import Schema, Source
from agentic_factory.job.submission.schema import submission_schema
from agentic_factory.job.submission.submit import NoSchemaSaved, submit, submitted

OUTPUT: Schema = {
    "type": "object",
    "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
    "required": ["urls"],
}
REPORT: dict[str, Any] = {
    "task": "Fetch the urls.",
    "done": ["urls.json written"],
    "not_done": [],
    "problems": [],
    "verdict": "done",
}


def text(report: dict[str, Any], output: Any = None) -> str:
    submission: dict[str, Any] = {"report": report}
    if output is not None:
        submission["output"] = output
    return json.dumps(submission)


@pytest.fixture
async def store() -> AsyncIterator[Store]:
    store = Store.from_url("sqlite+aiosqlite:///:memory:")
    await store.create_all()
    for session_id, output in (("plain", None), ("s1", OUTPUT)):
        await store.start_session(session_id, "claude", "m", "/w", "fetch")
        await store.save_output_schema(session_id, submission_schema(output))
    yield store
    await store.dispose()


async def test_a_report_only_submission_saves_the_report_and_no_output(store: Store) -> None:
    checked = await submit(store, "plain", text(REPORT))
    assert checked.errors == []
    row = await store.load_report("plain")
    assert row is not None and row.report == REPORT and row.verdict == "done"
    assert await store.load_structured_output("plain") is None
    found = await submitted(store, "plain")
    assert found is not None and found.report.verdict == Verdict.DONE and found.output is None


async def test_a_submission_with_output_saves_both_parts(store: Store) -> None:
    checked = await submit(store, "s1", text(REPORT, {"urls": ["u"]}))
    assert checked.errors == []
    row = await store.load_structured_output("s1")
    assert row is not None and row.source == Source.SUBMITTED
    assert row.schema == submission_schema(OUTPUT)
    found = await submitted(store, "s1")
    assert found is not None and found.output == {"urls": ["u"]}
    assert found.report.task == "Fetch the urls."


async def test_an_invalid_submission_saves_nothing(store: Store) -> None:
    checked = await submit(store, "s1", text(REPORT, {"urls": [1]}))
    assert checked.errors == ["output.urls[0]: 1 is not of type 'string'"]
    assert await store.load_report("s1") is None
    assert await store.load_structured_output("s1") is None
    assert await submitted(store, "s1") is None


async def test_a_later_valid_submission_replaces_the_earlier_one(store: Store) -> None:
    partial = {**REPORT, "verdict": "partial"}
    await submit(store, "s1", text(partial, {"urls": ["a"]}))
    await submit(store, "s1", text(REPORT, {"urls": [2]}))
    await submit(store, "s1", text(REPORT, {"urls": ["b"]}))
    found = await submitted(store, "s1")
    assert found is not None and found.output == {"urls": ["b"]}
    assert found.report.verdict == Verdict.DONE


async def test_a_session_with_no_schema_is_refused(store: Store) -> None:
    with pytest.raises(NoSchemaSaved):
        await submit(store, "nobody", "{}")
