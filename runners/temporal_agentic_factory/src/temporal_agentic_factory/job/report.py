from factory_store.store import Store
from pydantic import BaseModel
from temporalio import activity

from agentic_factory.failure import JobFailed
from agentic_factory.job.contract import JobResult
from agentic_factory.job.report import build as reports
from agentic_factory.job.report.contract import JobReport
from agentic_factory.settings.load import settings
from agentic_factory.step.providers.catalog import client_for
from temporal_agentic_factory.failure import to_application_error


class ReportRequest(BaseModel):
    """What the report is about: the session, and how the job ended."""

    session_id: str
    result: JobResult | None = None
    failure: str = ""


class ReportActivity:
    def __init__(self, store: Store) -> None:
        self.store = store

    @activity.defn
    async def build_report(self, request: ReportRequest) -> JobReport:
        """After the job's last try, the report over everything it stored.
        What the report is and what is saved is the app's `build_report`; this
        activity gives it the store and the client for the step provider from
        settings, and types its failure for Temporal."""
        client = client_for(settings.step.provider)
        try:
            return await reports.build_report(
                self.store, request.session_id, request.result, request.failure, client
            )
        except JobFailed as failure:
            raise to_application_error(failure) from failure
