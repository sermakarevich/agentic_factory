from factory_store.store import Store
from pydantic import BaseModel
from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job.contract import JobResult
from agentic_factory.job.report import conversation
from agentic_factory.job.report import step as reports
from agentic_factory.job.report.contract import JobReport
from agentic_factory.settings.load import settings
from agentic_factory.step.providers.catalog import client_for
from temporal_agentic_factory.activities.failure import to_application_error
from temporal_agentic_factory.activities.store import store


class ReportRequest(BaseModel):
    session_id: str
    result: JobResult | None = None
    failure: str = ""


@activity.defn
async def build_report(request: ReportRequest) -> JobReport:
    """After the job's last try: the stored events become the conversation,
    saved, and one model step reads it and writes the report, saved too."""
    db = store()
    text = await _saved_conversation(db, request.session_id)
    report = await _written_report(text, request)
    await _save_report(db, request, report)
    return report


async def _saved_conversation(db: Store, session_id: str) -> str:
    """The session's stored events rendered as one text, kept beside them."""
    rows = await db.load_events(session_id)
    text = conversation.render(rows)
    await db.save_conversation(session_id, text, len(rows))
    return text


async def _written_report(text: str, request: ReportRequest) -> JobReport:
    """The report step over the conversation, with the client for the step
    provider from settings; its failure typed for Temporal."""
    try:
        client = client_for(settings.step.provider)
        return await reports.report(text, request.result, request.failure, client)
    except JobFailed as failure:
        raise to_application_error(failure) from failure


async def _save_report(db: Store, request: ReportRequest, report: JobReport) -> None:
    result = request.result.model_dump(mode="json") if request.result else {}
    await db.save_report(request.session_id, result, report.model_dump(mode="json"), report.verdict)
