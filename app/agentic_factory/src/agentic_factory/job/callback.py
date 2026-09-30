from pydantic import BaseModel, Field

from agentic_factory.callback import Callback
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.stats import JobStats
from agentic_factory.tokens import Tokens


class JobEnd(BaseModel):
    """How a run ended, for `on_end`: the result, or the failure's text, and
    what the ledger counted either way; on a failure, the turns so far."""

    result: JobResult | None = None
    failure: str = Field(
        default="",
        description="`Kind: message` of the error, or `cancelled`; empty with a result.",
    )
    tokens: Tokens
    cost_usd: float = Field(description="Known before the end only for coders that price turns.")
    duration_sec: float
    stats: JobStats

    @property
    def done(self) -> bool:
        return self.result is not None


class JobCallback(Callback):
    """What a job run tells whoever listens: that it starts, every event as
    it happens, and how it ended. The runner fans out to a heartbeat, a log
    and a journal callback; the engine does not know who listens."""

    async def on_start(self, job: Job) -> None:
        """The job as it will run: defaults filled, session made."""
        return

    async def on_end(self, end: JobEnd) -> None:
        """Once per run: on a result, on any error and on a cancellation alike."""
        return
