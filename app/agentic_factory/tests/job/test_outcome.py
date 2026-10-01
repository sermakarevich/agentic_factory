from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome, verdict_of, with_follow_up_spend
from agentic_factory.job.report.contract import Verdict
from agentic_factory.job.report.failure import failed_report
from agentic_factory.tokens import Tokens


def result(cost: float, tokens: int, known: bool = True) -> JobResult:
    return JobResult(
        cost_usd=cost, tokens=Tokens(input=tokens), duration_sec=1.0, usage_known=known
    )


def test_a_follow_up_adds_its_spend_to_the_result() -> None:
    outcome = JobOutcome(session_id="s1", result=result(0.5, 100))
    added = with_follow_up_spend(outcome, result(0.25, 10, known=False))
    assert added.result is not None
    assert (added.result.cost_usd, added.result.tokens.input) == (0.75, 110)
    assert added.result.duration_sec == 2.0 and added.result.usage_known is False


def test_a_follow_up_with_no_result_changes_nothing() -> None:
    outcome = JobOutcome(session_id="s1", result=result(0.5, 100))
    assert with_follow_up_spend(outcome, None) == outcome


def test_the_verdict_is_the_reports_or_unknown_without_one() -> None:
    job = Job(name="plan", prompt="p", workdir="/w")
    failed = JobOutcome(session_id="s1", report=failed_report(job, "Stalled: quiet"))
    assert verdict_of(failed) == Verdict.FAILED
    assert verdict_of(JobOutcome(session_id="s1")) == Verdict.UNKNOWN


def test_a_failed_report_is_written_by_code_from_the_failure() -> None:
    job = Job(prompt="Fetch the urls.\nThen more.", workdir="/w")
    report = failed_report(job, "Stalled: quiet")
    assert report.task == "Fetch the urls." and report.problems == ["Stalled: quiet"]
    assert report.done == [] and report.not_done == [] and report.verdict == Verdict.FAILED
