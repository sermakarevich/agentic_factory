import json

import pytest

from agentic_factory.failure import JobFailed
from agentic_factory.job.contract import JobResult
from agentic_factory.job.report import SYSTEM_PROMPT, JobReport, Verdict, prompt_for, report
from agentic_factory.settings.load import settings
from agentic_factory.step.client import Answer, Client
from agentic_factory.step.contract import Step


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


async def test_report_sends_the_transcript_and_parses_the_verdict() -> None:
    client = ScriptedClient(
        json.dumps({"task": "t", "done": ["a"], "not_done": [], "problems": [], "verdict": "done"})
    )
    assert await report("hello", JobResult(summary_text='{"job_summary": 1}'), "", client) == (
        JobReport(task="t", done=["a"], not_done=[], problems=[], verdict=Verdict.DONE)
    )
    (step,) = client.steps
    assert step.prompt.startswith("TRANSCRIPT\nhello")
    assert "The coder's own summary:" in step.prompt
    assert step.output_schema == JobReport.model_json_schema()
    assert step.system_prompt == SYSTEM_PROMPT


def test_prompt_mentions_the_failure_when_there_is_no_summary() -> None:
    assert prompt_for("c", None, "Stalled: quiet").endswith("The last try failed: Stalled: quiet")
    assert prompt_for("c", None, "").endswith("No summary and no failure recorded.")


def test_prompt_clips_a_long_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.report, "max_chars", 50)
    prompt = prompt_for("x" * 500, None, "")
    assert "[...]" in prompt
    transcript = prompt.split("\n\nENDING\n")[0].removeprefix("TRANSCRIPT\n")
    assert len(transcript) <= 50


async def test_bad_answer_raises() -> None:
    with pytest.raises(JobFailed):
        await report("hello", None, "", ScriptedClient("not json"))
