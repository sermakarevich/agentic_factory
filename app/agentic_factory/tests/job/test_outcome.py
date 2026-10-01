from agentic_factory.job.contract import JobResult
from agentic_factory.job.outcome import JobOutcome, with_follow_up_spend
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
