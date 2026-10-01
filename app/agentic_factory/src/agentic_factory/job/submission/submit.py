from typing import Any

from factory_store.store import Store
from pydantic import BaseModel

from agentic_factory.job.report.contract import JobReport
from agentic_factory.job.submission.check import Checked, check
from agentic_factory.job.submission.contract import Schema, Source
from agentic_factory.job.submission.schema import OUTPUT_KEY, REPORT_KEY, asks_for_output


class NoSchemaSaved(Exception):
    """No submission schema is saved for the session: an unknown session id."""


class Submitted(BaseModel):
    """What the coder submitted: its report and, when the job asked for one,
    its output."""

    report: JobReport
    output: dict[str, Any] | None = None


async def submit(store: Store, session_id: str, text: str) -> Checked:
    """The coder's JSON checked against the session's saved schema and, when
    it matches, saved: the report in the report table and, when the job asked
    for one, the output as its structured output. Each replaces an earlier
    one. Nothing is saved when it does not match. Raises `NoSchemaSaved`
    when the session has no schema."""
    schema = await saved_schema(store, session_id)
    checked = check(text, schema)
    if checked.submission is not None:
        await save(store, session_id, schema, checked.submission)
    return checked


async def save(store: Store, session_id: str, schema: Schema, submission: dict[str, Any]) -> None:
    """Both parts of a submission that matched the schema, each where it is kept."""
    report = submission[REPORT_KEY]
    await store.save_report(session_id, report, report["verdict"])
    if asks_for_output(schema):
        await store.save_structured_output(
            session_id, schema, submission[OUTPUT_KEY], Source.SUBMITTED
        )


async def saved_schema(store: Store, session_id: str) -> Schema:
    """The schema the workflow saved for the session before the coder started."""
    schema = await store.load_output_schema(session_id)
    if schema is None:
        raise NoSchemaSaved(f"no submission schema is saved for session {session_id}")
    return schema


async def submitted(store: Store, session_id: str) -> Submitted | None:
    """The coder's last valid submission, or None when it submitted none."""
    row = await store.load_report(session_id)
    if row is None:
        return None
    report = JobReport.model_validate(row.report)
    return Submitted(report=report, output=await submitted_output(store, session_id))


async def submitted_output(store: Store, session_id: str) -> dict[str, Any] | None:
    """The submitted output, or None when the job was asked for none."""
    row = await store.load_structured_output(session_id)
    if row is None or row.source != Source.SUBMITTED:
        return None
    return row.structured_output
