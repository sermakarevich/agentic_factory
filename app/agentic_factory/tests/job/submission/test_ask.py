from typing import Any

from agentic_factory.job.coders.claude.harness import ClaudeHarness
from agentic_factory.job.coders.opencode.harness import OpencodeHarness
from agentic_factory.job.contract import Job
from agentic_factory.job.submission.ask import ask_for_submission, asked_job
from agentic_factory.job.submission.contract import Schema

SCHEMA: Schema = {"type": "object", "properties": {"urls": {"type": "array"}}}


class FakeStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, Schema]] = []
        self.calls: list[str] = []

    async def forget_submission(self, session_id: str) -> None:
        self.calls.append(f"forget {session_id}")

    async def save_output_schema(self, session_id: str, schema: dict[str, Any]) -> None:
        self.saved.append((session_id, schema))
        self.calls.append(f"save {session_id}")


def job(provider: str, tools: list[str]) -> Job:
    return Job(provider=provider, prompt="fetch", workdir="/w", session_id="s1", tools=tools)


async def test_the_schema_is_saved_under_the_session_and_the_prompt_names_it() -> None:
    store = FakeStore()
    claude = ClaudeHarness()
    asked = await ask_for_submission(store, job("claude", []), SCHEMA, "/v/af", claude)  # type: ignore[arg-type]
    assert store.saved == [("s1", SCHEMA)]
    assert store.calls == ["forget s1", "save s1"]
    assert asked.command == "/v/af output submit s1"
    assert asked.job.prompt.startswith("fetch\n\n") and asked.command in asked.job.prompt
    assert asked.job.tools == [] and asked.job.session_id == "s1"


def test_claude_with_restricted_tools_is_allowed_the_submit_command() -> None:
    asked = asked_job(job("claude", ["Read", "Edit"]), SCHEMA, "/v/af", ClaudeHarness())
    assert asked.job.tools == ["Read", "Edit", "Bash(/v/af output submit:*)"]


def test_opencode_tools_are_left_as_they_are_since_it_enforces_none() -> None:
    asked = asked_job(job("opencode", ["read"]), SCHEMA, "/v/af", OpencodeHarness())
    assert asked.job.tools == ["read"]
