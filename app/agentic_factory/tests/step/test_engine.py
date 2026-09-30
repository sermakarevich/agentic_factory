import asyncio
import json

import pytest
from pydantic import BaseModel

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import BadOutput, TimedOut
from agentic_factory.step.contract import Step
from agentic_factory.step.engine import run
from agentic_factory.step.providers.client import Answer, Client
from agentic_factory.tokens import Tokens


class Report(BaseModel):
    status: str
    summary: str


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    async def on_event(self, event: Event) -> None:
        self.events.append(event)


class ScriptedClient(Client):
    """Answers with a fixed text and remembers the step it got."""

    default_model = "scripted-1"

    def __init__(self, text: str) -> None:
        self.text = text
        self.steps: list[Step] = []

    @classmethod
    def from_env(cls) -> "ScriptedClient":
        return cls("{}")

    async def complete(self, step: Step) -> Answer:
        self.steps.append(step)
        return Answer(text=self.text, tokens=Tokens(input=10, output=20))


def step(**overrides: object) -> Step:
    base = {"prompt": "Report.", "output_schema": Report.model_json_schema()}
    return Step.model_validate({**base, **overrides})


async def test_answer_becomes_events_and_a_typed_result() -> None:
    answer = json.dumps({"status": "done", "summary": "wrote hello.txt"})
    client = ScriptedClient(answer)
    observer = Recorder()

    result = await run(step(), observer, client)

    assert client.steps[0].model == "scripted-1"  # default filled before the client sees it
    assert [e.kind for e in observer.events] == [EventKind.AI, EventKind.FINISHED]
    assert observer.events[0].content == answer
    assert observer.events[1].usage == Tokens(input=10, output=20)
    assert result.parse(Report) == Report(status="done", summary="wrote hello.txt")
    assert result.model == "scripted-1"
    assert result.tokens == Tokens(input=10, output=20)


async def test_answer_that_is_not_an_object_is_bad_output_after_the_ai_event() -> None:
    observer = Recorder()
    with pytest.raises(BadOutput, match="not JSON"):
        await run(step(), observer, ScriptedClient("sure, here you go"))
    assert [e.kind for e in observer.events] == [EventKind.AI]
    with pytest.raises(BadOutput, match="not a JSON object"):
        await run(step(), Recorder(), ScriptedClient("[1, 2]"))


async def test_answer_that_misses_the_schema_fails_at_parse() -> None:
    result = await run(step(), Recorder(), ScriptedClient('{"status": "done"}'))
    assert result.output == {"status": "done"}
    with pytest.raises(BadOutput, match="does not match Report"):
        result.parse(Report)


async def test_slow_client_is_timed_out() -> None:
    class Hanging(ScriptedClient):
        async def complete(self, step: Step) -> Answer:
            await asyncio.sleep(5)
            return Answer(text="{}")

    with pytest.raises(TimedOut, match="exceeded 0s"):
        await run(step(timeout_sec=0), Recorder(), Hanging("{}"))
