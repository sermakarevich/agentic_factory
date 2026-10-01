import asyncio
import json

import pytest

from agentic_factory.callback import Callback
from agentic_factory.event import Event, EventKind
from agentic_factory.failure import BadOutput, TimedOut
from agentic_factory.step.judge.answer import CheckAnswer, ChoiceAnswer
from agentic_factory.step.judge.client import JudgeClient, JudgeReply
from agentic_factory.step.judge.contract import Judgment
from agentic_factory.step.judge.engine import run
from agentic_factory.tokens import Tokens

ANSWERS = {
    "tone": ChoiceAnswer(choice="calm", confidence=0.9, probabilities={"calm": 0.9, "angry": 0.1}),
    "billing": CheckAnswer(yes=0.8),
}


class Recorder(Callback):
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def on_event(self, event: Event) -> None:
        self.events.append(event)


class ScriptedJudge(JudgeClient):
    """Replies with fixed answers and remembers the judgment it got."""

    default_model = "jev-scripted"

    def __init__(self) -> None:
        self.judgments: list[Judgment] = []

    @classmethod
    def from_env(cls) -> "ScriptedJudge":
        return cls()

    async def answer(self, judgment: Judgment) -> JudgeReply:
        self.judgments.append(judgment)
        return JudgeReply(answers=ANSWERS, tokens=Tokens(input=120), cost_usd=0.000005)


def judgment(**overrides: object) -> Judgment:
    base = {
        "state": "I was charged twice. Please help.",
        "questions": {
            "tone": {
                "kind": "choice",
                "question": "Tone?",
                "options": {"calm": None, "angry": None},
            },
            "billing": {"kind": "check", "question": "About billing?"},
        },
    }
    return Judgment.model_validate({**base, **overrides})


async def test_answers_become_events_and_a_typed_result() -> None:
    client = ScriptedJudge()
    observer = Recorder()

    result = await run(judgment(), observer, client)

    assert client.judgments[0].model == "jev-scripted"  # default filled before the client sees it
    assert [e.kind for e in observer.events] == [EventKind.AI, EventKind.FINISHED]
    assert json.loads(observer.events[0].content)["tone"]["choice"] == "calm"
    assert observer.events[1].usage == Tokens(input=120) and observer.events[1].cost_usd > 0
    assert result.choice("tone").choice == "calm" and result.check("billing").yes == 0.8
    assert result.model == "jev-scripted" and result.cost_usd == 0.000005


async def test_an_answer_of_another_kind_or_name_is_bad_output() -> None:
    result = await run(judgment(), Recorder(), ScriptedJudge())
    with pytest.raises(BadOutput, match="is a choice, not a ScoreAnswer"):
        result.score("tone")
    with pytest.raises(BadOutput, match="no answer named 'risk'"):
        result.check("risk")


async def test_slow_judge_is_timed_out() -> None:
    class Hanging(ScriptedJudge):
        async def answer(self, judgment: Judgment) -> JudgeReply:
            await asyncio.sleep(5)
            return JudgeReply(answers={})

    with pytest.raises(TimedOut, match="exceeded 0s"):
        await run(judgment(timeout_sec=0), Recorder(), Hanging())


def test_a_judgment_needs_at_least_one_question_and_two_options() -> None:
    with pytest.raises(ValueError, match="questions"):
        judgment(questions={})
    with pytest.raises(ValueError, match="options"):
        judgment(questions={"t": {"kind": "choice", "question": "?", "options": {"one": None}}})
