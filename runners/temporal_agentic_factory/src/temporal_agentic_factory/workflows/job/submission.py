import sys
from pathlib import Path

from factory_store.store import Store
from pydantic import BaseModel
from temporalio import activity

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.submission import submit
from agentic_factory.job.submission.ask import AskedJob, ask_for_submission
from agentic_factory.job.submission.contract import Schema
from agentic_factory.job.submission.schema import submission_schema
from agentic_factory.job.submission.submit import Submitted

AF = "af"  # the cli's script name, installed beside the Python that runs it


class SubmissionRequest(BaseModel):
    """A job whose session is made, and the schema of the output it must
    hand back, when it must hand one back."""

    job: Job
    output_schema: Schema | None = None


class SubmissionActivity:
    def __init__(self, store: Store) -> None:
        self.store = store

    @activity.defn
    async def ask_for_submission(self, request: SubmissionRequest) -> AskedJob:
        """The app's `ask_for_submission`: the submission schema saved before
        the coder starts, the job asked to submit with this install's `af`, by
        its absolute path, as a coder's PATH need not hold it."""
        job = request.job
        schema = submission_schema(request.output_schema)
        return await ask_for_submission(
            self.store, job, schema, af_path(), harness_for(job.provider)
        )

    @activity.defn
    async def read_submission(self, session_id: str) -> Submitted | None:
        """The coder's last valid `af output submit`, or None when it made none."""
        return await submit.submitted(self.store, session_id)


def af_path() -> str:
    """The `af` of this install, beside the running Python; plain `af` when
    it is not there (a run from outside the installed environment)."""
    beside = Path(sys.executable).with_name(AF)
    return str(beside) if beside.exists() else AF
