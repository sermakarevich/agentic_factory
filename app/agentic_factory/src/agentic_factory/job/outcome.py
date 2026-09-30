from pydantic import BaseModel, Field

from agentic_factory.job.contract import JobResult
from agentic_factory.job.report.contract import JobReport


class JobOutcome(BaseModel):
    """What a job workflow returns: the engine's result (None when every try
    failed) and the report a model wrote over the whole session."""

    session_id: str
    result: JobResult | None = None
    failure: str = Field(default="", description="The last try's failure, when there is no result.")
    report: JobReport | None = Field(default=None, description="None when the report step failed.")
