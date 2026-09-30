from pydantic import BaseModel
from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job import conversation
from agentic_factory.job import report as reports
from agentic_factory.job.contract import JobResult
from agentic_factory.job.report import JobReport
from agentic_factory.settings.load import settings
from agentic_factory.step.catalog import client_for
from temporal_agentic_factory.failure import to_application_error
from temporal_agentic_factory.store import store


class ReportRequest(BaseModel):
    session_id: str
    result: JobResult | None = None
    failure: str = ""


@activity.defn
async def build_report(request: ReportRequest) -> JobReport:
    """After the job's last try: the stored events become the conversation,
    saved, and one model step reads it and writes the report, saved too."""
    db = store()
    rows = await db.load_events(request.session_id)
    text = conversation.render(rows)
    await db.save_conversation(request.session_id, text, len(rows))
    try:
        client = client_for(settings.step.provider)
        report = await reports.report(text, request.result, request.failure, client)
    except JobFailed as failure:
        raise to_application_error(failure) from failure
    result = request.result.model_dump(mode="json") if request.result else {}
    await db.save_report(request.session_id, result, report.model_dump(mode="json"), report.verdict)
    return report
