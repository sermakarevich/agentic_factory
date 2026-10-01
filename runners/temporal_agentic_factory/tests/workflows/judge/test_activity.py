from datetime import UTC, datetime, timedelta

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.callback import Callback
from agentic_factory.failure import RateLimited
from agentic_factory.step.judge.answer import CheckAnswer
from agentic_factory.step.judge.client import JudgeClient
from agentic_factory.step.judge.contract import Judgment, JudgmentResult
from temporal_agentic_factory.workflows.judge import activity

JUDGMENT = Judgment.model_validate(
    {
        "state": "I was charged twice.",
        "questions": {"billing": {"kind": "check", "question": "About billing?"}},
    }
)
RESULT = JudgmentResult(answers={"billing": CheckAnswer(yes=0.8)}, model="jev-latest")


class StubJudge(JudgeClient):
    default_model = "jev-stub"

    @classmethod
    def from_env(cls) -> "StubJudge":
        return cls()

    async def answer(self, judgment: Judgment):  # type: ignore[no-untyped-def]
        raise AssertionError("the engine is stubbed; the client is never asked")


async def test_the_app_judges_with_the_providers_client(monkeypatch: pytest.MonkeyPatch) -> None:
    given: list[tuple[Judgment, Callback, JudgeClient]] = []

    async def fake_run(
        judgment: Judgment, callback: Callback, client: JudgeClient
    ) -> JudgmentResult:
        given.append((judgment, callback, client))
        return RESULT

    monkeypatch.setattr(activity, "judge_for", lambda provider: StubJudge())
    monkeypatch.setattr(activity.engine, "run", fake_run)
    found = await ActivityEnvironment().run(activity.judge, JUDGMENT)

    assert found == RESULT
    ((judgment, callback, client),) = given
    assert judgment == JUDGMENT and isinstance(client, StubJudge)
    assert type(callback) is Callback  # events go nowhere: the answers are the result


async def test_a_rate_limit_becomes_a_typed_error_with_a_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(
        judgment: Judgment, callback: Callback, client: JudgeClient
    ) -> JudgmentResult:
        raise RateLimited(datetime.now(UTC) + timedelta(seconds=30))

    monkeypatch.setattr(activity, "judge_for", lambda provider: StubJudge())
    monkeypatch.setattr(activity.engine, "run", fake_run)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(activity.judge, JUDGMENT)
    assert err.value.type == "RateLimited" and not err.value.non_retryable
    assert err.value.next_retry_delay is not None
