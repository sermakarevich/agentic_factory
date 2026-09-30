from factory_store.store import Store

from agentic_factory.job.contract import JobResult
from agentic_factory.job.report.contract import JobReport
from agentic_factory.job.report.conversation import render
from agentic_factory.job.report.step import report
from agentic_factory.step.providers.client import Client


async def build_report(
    store: Store, session_id: str, result: JobResult | None, failure: str, client: Client
) -> JobReport:
    """After the job's last try: the session's stored events become the
    conversation, saved beside them; one model step reads it and writes the
    report, saved too. Raises the step's `JobFailed` when the model could
    not answer; the report row is then not written."""
    text = await _saved_conversation(store, session_id)
    written = await report(text, result, failure, client)
    await _save_report(store, session_id, result, written)
    return written


async def _saved_conversation(store: Store, session_id: str) -> str:
    rows = await store.load_events(session_id)
    text = render(rows)
    await store.save_conversation(session_id, text, len(rows))
    return text


async def _save_report(
    store: Store, session_id: str, result: JobResult | None, written: JobReport
) -> None:
    result_json = result.model_dump(mode="json") if result else {}
    await store.save_report(
        session_id, result_json, written.model_dump(mode="json"), written.verdict
    )
