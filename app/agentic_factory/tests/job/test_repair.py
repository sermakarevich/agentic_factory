import json

from agentic_factory.job.repair import repair_summary
from agentic_factory.job.summary import JobSummary
from agentic_factory.step.client import Answer, Client
from agentic_factory.step.contract import Step

FIXED = {"task": "t", "plan": ["a"], "execution": ["b"], "result": "r", "success": False}


class ScriptedClient(Client):
    default_model = "scripted-1"

    def __init__(self, text: str) -> None:
        self.text = text
        self.steps: list[Step] = []

    @classmethod
    def from_env(cls) -> "ScriptedClient":
        return cls("{}")

    async def complete(self, step: Step) -> Answer:
        self.steps.append(step)
        return Answer(text=self.text)


async def test_repair_sends_the_block_with_the_schema_and_parses_the_answer() -> None:
    client = ScriptedClient(json.dumps(FIXED))
    assert await repair_summary('{"job_summary": {"task": "t", "plan": ["a"', client) == (
        JobSummary(**FIXED)
    )
    (step,) = client.steps
    assert step.prompt.startswith('{"job_summary"') and "job_summary" in step.system_prompt
    assert step.output_schema == JobSummary.model_json_schema()


async def test_repair_gives_none_when_the_model_cannot_fix_it_either() -> None:
    assert await repair_summary("{", ScriptedClient("not json")) is None
    assert await repair_summary("{", ScriptedClient('{"task": "only"}')) is None
