from datetime import UTC, datetime

from factory_store.schema import Outcome
from factory_store.store import JobRecord, Store, StoredTry, Totals

from agentic_factory.job.outcome import JobOutcome


async def record_job(store: Store, outcome: JobOutcome) -> None:
    """The `job` row, one per workflow run: its tries as the store has them,
    summed, with how the job ended and the report's verdict. Written once at
    the end, after the report; a second call replaces the row."""
    tries = await store.load_tries(outcome.session_id)
    await store.save_job(outcome.session_id, job_record(outcome, tries, datetime.now(UTC)))


def job_record(outcome: JobOutcome, tries: list[StoredTry], now: datetime) -> JobRecord:
    return JobRecord(
        started_at=tries[0].started_at if tries else now,
        ended_at=now,
        tries=len(tries),
        outcome=Outcome.DONE if outcome.result else Outcome.FAILED,
        failure=outcome.failure,
        totals=sum((t.totals for t in tries), Totals()),
        result=outcome.result.model_dump(mode="json") if outcome.result else {},
        verdict=outcome.report.verdict.value if outcome.report else "",
    )
