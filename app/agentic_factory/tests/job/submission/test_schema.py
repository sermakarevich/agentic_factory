import json
from enum import StrEnum
from typing import Any

import pytest
from pydantic import BaseModel, Field

from agentic_factory.job.report.contract import JobReport
from agentic_factory.job.submission.check import check
from agentic_factory.job.submission.schema import (
    ClashingDefs,
    asks_for_output,
    merged_defs,
    submission_schema,
)


# The tutorial plan's nested shape, rebuilt here: an app never imports another app.
class Format(StrEnum):
    MD = "md"
    IPYNB = "ipynb"


class Chapter(BaseModel):
    slug: str
    formats: list[Format] = Field(description="The files the chapter is written as.")


class Plan(BaseModel):
    name: str
    chapters: list[Chapter]


REPORT: dict[str, Any] = {
    "task": "Plan the tutorial.",
    "done": ["plan.md written"],
    "not_done": [],
    "problems": [],
    "verdict": "done",
}
PLAN: dict[str, Any] = {"name": "jq", "chapters": [{"slug": "a", "formats": ["md"]}]}


def test_a_report_only_schema_asks_for_the_report_and_nothing_else() -> None:
    schema = submission_schema(None)
    assert schema["required"] == ["report"] and not asks_for_output(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["report"]["properties"].keys() == JobReport.model_fields.keys()
    assert check(json.dumps({"report": REPORT}), schema).errors == []


def test_the_coder_may_not_send_unknown() -> None:
    verdict = submission_schema(None)["properties"]["report"]["properties"]["verdict"]
    assert verdict["enum"] == ["done", "partial", "failed"]


def test_the_output_defs_move_to_the_top_where_their_refs_resolve() -> None:
    schema = submission_schema(Plan.model_json_schema())
    assert schema["required"] == ["report", "output"] and asks_for_output(schema)
    assert set(schema["$defs"]) == {"Chapter", "Format"}
    assert "$defs" not in schema["properties"]["output"]
    checked = check(json.dumps({"report": REPORT, "output": PLAN}), schema)
    assert checked.errors == [] and checked.submission is not None
    assert Plan.model_validate(checked.submission["output"]).chapters[0].formats == [Format.MD]


def test_a_wrong_enum_deep_in_the_output_shows_its_path() -> None:
    bad = {"name": "jq", "chapters": [PLAN["chapters"][0], {"slug": "b", "formats": ["pdf"]}]}
    checked = check(
        json.dumps({"report": REPORT, "output": bad}), submission_schema(Plan.model_json_schema())
    )
    assert checked.errors == ["output.chapters[1].formats[0]: 'pdf' is not one of ['md', 'ipynb']"]


def test_a_missing_report_is_an_error_line() -> None:
    checked = check(json.dumps({"output": PLAN}), submission_schema(Plan.model_json_schema()))
    assert checked.submission is None
    assert checked.errors == ["(top): 'report' is a required property"]


def test_a_bad_verdict_is_an_error_line_with_its_path() -> None:
    report = {**REPORT, "verdict": "unknown"}
    checked = check(json.dumps({"report": report}), submission_schema(None))
    assert checked.errors == [
        "report.verdict: 'unknown' is not one of ['done', 'partial', 'failed']"
    ]


def test_two_parts_defining_one_name_differently_are_refused() -> None:
    first = {"$defs": {"Format": {"type": "string"}}}
    assert merged_defs([first, first]) == first["$defs"]
    with pytest.raises(ClashingDefs):
        merged_defs([first, {"$defs": {"Format": {"type": "integer"}}}])
