from datetime import UTC, datetime, timedelta

from factory_store.schema import Outcome
from factory_store.store import StoredTry, Totals

from agentic_factory.job.contract import JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.record import job_record
from agentic_factory.job.report.contract import JobReport, Verdict

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)


def stored_try(attempt: int, outcome: str, totals: Totals) -> StoredTry:
    started = NOW - timedelta(minutes=10 - attempt)
    return StoredTry(
        session_id="s1",
        attempt=attempt,
        started_at=started,
        ended_at=started + timedelta(minutes=1),
        outcome=outcome,
        failure="" if outcome == "done" else "Stalled: quiet",
        totals=totals,
        result={},
    )


def report(verdict: Verdict) -> JobReport:
    return JobReport(task="t", done=[], not_done=[], problems=[], verdict=verdict)


def test_a_done_job_sums_its_tries_and_keeps_the_verdict() -> None:
    tries = [
        stored_try(1, "failed", Totals(input_tokens=100, cost_usd=0.1, turns=2)),
        stored_try(2, "done", Totals(input_tokens=50, cost_usd=0.05, turns=1)),
    ]
    result = JobResult(session_id="s1", cost_usd=0.05)
    outcome = JobOutcome(session_id="s1", result=result, report=report(Verdict.PARTIAL))
    record = job_record(outcome, tries, NOW)
    assert record.outcome == Outcome.DONE and record.failure == ""
    assert record.tries == 2 and record.verdict == "partial"
    assert record.totals == Totals(input_tokens=150, cost_usd=0.15000000000000002, turns=3)
    assert record.started_at == tries[0].started_at and record.ended_at == NOW
    assert record.result == result.model_dump(mode="json")


def test_a_failed_job_without_a_report_has_no_verdict() -> None:
    outcome = JobOutcome(session_id="s1", failure="Stalled: quiet")
    record = job_record(outcome, [], NOW)
    assert record.outcome == Outcome.FAILED and record.failure == "Stalled: quiet"
    assert record.tries == 0 and record.verdict == "" and record.result == {}
    assert record.started_at == NOW and record.totals == Totals()
