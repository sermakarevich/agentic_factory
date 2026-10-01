import sys
from pathlib import Path
from typing import Any

from factory_store.store import Store
from pydantic import BaseModel
from temporalio import activity

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.structured_output import submission
from agentic_factory.job.structured_output.ask import AskedJob, ask_for_submission
from agentic_factory.job.structured_output.contract import Schema

AF = "af"  # the cli's script name, installed beside the Python that runs it


class SubmissionRequest(BaseModel):
    """A job whose session is made, and the schema its submission is checked against."""

    job: Job
    output_schema: Schema


class SubmissionActivity:
    def __init__(self, store: Store) -> None:
        self.store = store

    @activity.defn
    async def ask_for_submission(self, request: SubmissionRequest) -> AskedJob:
        """The app's `ask_for_submission`: the schema saved before the coder
        starts, the job asked to submit with this install's `af`, by its
        absolute path, as a coder's PATH need not hold it."""
        job = request.job
        harness = harness_for(job.provider)
        return await ask_for_submission(self.store, job, request.output_schema, af_path(), harness)

    @activity.defn
    async def read_submitted_output(self, session_id: str) -> dict[str, Any] | None:
        """The coder's last valid `af output submit`, or None when it made none."""
        return await submission.submitted_output(self.store, session_id)


def af_path() -> str:
    """The `af` of this install, beside the running Python; plain `af` when
    it is not there (a run from outside the installed environment)."""
    beside = Path(sys.executable).with_name(AF)
    return str(beside) if beside.exists() else AF
