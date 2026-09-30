import json

import pytest
from pydantic import BaseModel, ConfigDict

from agentic_factory.failure import JobFailed
from agentic_factory.job.structured_output.contract import Extraction
from agentic_factory.job.structured_output.step import (
    SYSTEM_PROMPT,
    extract,
    extraction_schema,
    prompt_for,
)
from agentic_factory.settings.load import settings
from agentic_factory.step.contract import Step
from agentic_factory.step.providers.client import Answer, Client


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


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[Page]


SCHEMA = StructuredOutput.model_json_schema()


async def test_extract_sends_the_text_with_the_wrapped_schema_and_parses_the_answer() -> None:
    client = ScriptedClient(
        json.dumps({"structured_output": {"pages": [{"url": "u"}]}, "missing": []})
    )
    assert await extract("pages: [{url: u}]", SCHEMA, client) == (
        Extraction(structured_output={"pages": [{"url": "u"}]}, missing=[])
    )
    (step,) = client.steps
    assert step.prompt == "pages: [{url: u}]"
    assert step.output_schema == extraction_schema(SCHEMA)
    assert step.system_prompt == SYSTEM_PROMPT


async def test_not_stated_is_an_answer_not_a_failure() -> None:
    client = ScriptedClient(json.dumps({"structured_output": None, "missing": ["pages"]}))
    assert await extract("all done", SCHEMA, client) == Extraction(
        structured_output=None, missing=["pages"]
    )


def test_the_wrapped_schema_allows_null_and_lifts_the_defs() -> None:
    wrapped = extraction_schema(SCHEMA)
    assert wrapped["required"] == ["structured_output", "missing"]
    assert wrapped["additionalProperties"] is False
    inner, null = wrapped["properties"]["structured_output"]["anyOf"]
    assert null == {"type": "null"} and "$defs" not in inner
    assert wrapped["$defs"] == SCHEMA["$defs"]
    assert SCHEMA.get("$defs")  # the input is untouched


def test_a_schema_with_no_defs_wraps_without_them() -> None:
    plain = {"type": "object", "properties": {"urls": {"type": "array"}}}
    assert "$defs" not in extraction_schema(plain)


def test_a_hand_written_schema_is_made_strict_at_every_level() -> None:
    loose = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "pages": {"type": "array", "items": {"type": "object", "properties": {"url": {}}}},
        },
    }
    inner, _ = extraction_schema(loose)["properties"]["structured_output"]["anyOf"]
    assert inner["required"] == ["path", "pages"] and inner["additionalProperties"] is False
    page = inner["properties"]["pages"]["items"]
    assert page["required"] == ["url"] and page["additionalProperties"] is False
    assert "required" not in loose  # the input is untouched


def test_prompt_clips_a_long_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.structured_output, "max_chars", 50)
    prompt = prompt_for("x" * 500)
    assert "[...]" in prompt and len(prompt) <= 50


async def test_bad_answer_raises() -> None:
    with pytest.raises(JobFailed):
        await extract("hello", SCHEMA, ScriptedClient("not json"))
