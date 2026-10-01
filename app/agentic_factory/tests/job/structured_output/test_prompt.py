import json

from pydantic import BaseModel

from agentic_factory.job.structured_output.prompt import command_prefix, submit_command, wrap_prompt
from agentic_factory.job.summary.prompt import wrap_prompt as wrap_summary


class Chapter(BaseModel):
    slug: str


class Plan(BaseModel):
    chapters: list[Chapter]


SCHEMA = Plan.model_json_schema()
COMMAND = "/venv/bin/af output submit s1"


def test_the_prompt_names_the_command_with_its_session_and_the_rules() -> None:
    wrapped = wrap_prompt("plan it", SCHEMA, COMMAND)
    assert wrapped.startswith("plan it\n\nBefore your final message, submit")
    assert f"{COMMAND} <<'JSON'\n{{ ... }}\nJSON\n" in wrapped
    assert "prints `ok`, or `invalid:`" in wrapped and "until it prints `ok`" in wrapped
    assert "the last submission that printed `ok` counts" in wrapped


def test_the_prompt_shows_the_whole_schema_with_its_defs_indented() -> None:
    wrapped = wrap_prompt("plan it", SCHEMA, COMMAND)
    assert wrapped.endswith(json.dumps(SCHEMA, indent=2))
    assert '"$defs"' in wrapped and '"$ref": "#/$defs/Chapter"' in wrapped


def test_the_submit_request_comes_before_the_summary_request() -> None:
    prompt = wrap_summary(wrap_prompt("do it", SCHEMA, COMMAND))
    assert prompt.index(COMMAND) < prompt.index("end your final message with this json block")


def test_the_command_quotes_a_path_with_spaces() -> None:
    assert command_prefix("/my venv/af") == "'/my venv/af' output submit"
    assert submit_command("af", "ses_1") == "af output submit ses_1"
