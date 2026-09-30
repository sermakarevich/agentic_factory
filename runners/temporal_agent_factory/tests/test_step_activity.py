import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agent_factory.event import Observer
from agent_factory.failure import BadOutput
from agent_factory.step.client import Client
from agent_factory.step.contract import Step, StepResult
from temporal_agent_factory.activities import step as activity

CALL = Step(prompt="p", output_schema={"type": "object"}, provider="opencode")


async def test_call_returns_the_engine_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(step: Step, observer: Observer, client: Client | None = None) -> StepResult:
        return StepResult(output={"ok": True}, model=step.model)

    monkeypatch.setattr(activity.steps, "run", fake_run)
    result = await ActivityEnvironment().run(activity.execute_step, CALL)
    assert result.output == {"ok": True}


async def test_bad_output_is_a_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(step: Step, observer: Observer, client: Client | None = None) -> StepResult:
        raise BadOutput("not json")

    monkeypatch.setattr(activity.steps, "run", fake_run)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(activity.execute_step, CALL)
    assert err.value.type == "BadOutput"
