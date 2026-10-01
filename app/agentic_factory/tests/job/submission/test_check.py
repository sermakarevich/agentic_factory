import json
from enum import StrEnum

from pydantic import BaseModel, Field

from agentic_factory.job.submission.check import check
from agentic_factory.job.submission.contract import Schema


# The tutorial plan's nested shape, rebuilt here: an app never imports another app.
class Format(StrEnum):
    MD = "md"
    IPYNB = "ipynb"


class Chapter(BaseModel):
    slug: str
    title: str
    formats: list[Format] = Field(description="The files the chapter is written as.")


class Plan(BaseModel):
    name: str
    chapters: list[Chapter]


SCHEMA: Schema = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "count": {"type": "integer"}},
    "required": ["title", "count"],
}
PLAN = Plan.model_json_schema()


def chapter(slug: str, formats: list[str]) -> dict[str, object]:
    return {"slug": slug, "title": slug.title(), "formats": formats}


def test_a_valid_object_is_returned_parsed() -> None:
    checked = check('{"title": "t", "count": 2}', SCHEMA)
    assert checked.submission == {"title": "t", "count": 2} and checked.errors == []


def test_a_missing_required_field_is_named_at_the_top() -> None:
    checked = check('{"title": "t"}', SCHEMA)
    assert checked.submission is None
    assert checked.errors == ["(top): 'count' is a required property"]


def test_a_wrong_enum_in_a_nested_list_item_shows_its_path() -> None:
    text = json.dumps({"name": "jq", "chapters": [chapter("a", ["md"]), chapter("b", ["pdf"])]})
    checked = check(text, PLAN)
    assert "$defs" in PLAN and checked.submission is None
    assert checked.errors == ["chapters[1].formats[0]: 'pdf' is not one of ['md', 'ipynb']"]


def test_every_error_is_listed() -> None:
    checked = check('{"title": 3}', SCHEMA)
    assert checked.errors == [
        "(top): 'count' is a required property",
        "title: 3 is not of type 'string'",
    ]


def test_bad_json_is_one_line_with_line_and_column() -> None:
    checked = check('{\n  "title": "t",\n}', SCHEMA)
    assert checked.submission is None
    assert checked.errors == [
        "not JSON: Illegal trailing comma before end of object at line 2 column 15"
    ]


def test_a_nested_object_from_a_pydantic_model_passes_and_keeps_its_nesting() -> None:
    plan = {"name": "jq", "chapters": [chapter("a", ["md", "ipynb"])]}
    checked = check(json.dumps(plan), PLAN)
    assert checked.submission == plan
    assert Plan.model_validate(checked.submission).chapters[0].formats[1] == "ipynb"


def test_json_that_is_not_an_object_is_refused() -> None:
    assert check("[1]", {}).errors == ["(top): the submission must be a JSON object"]
