"""The request's checks, and the build-order rules a requirements job's units must meet."""

import pytest
from pydantic import ValidationError

from autocode.contract import AutocodeRequest, Commands, Requirements, Unit
from autocode.settings.load import settings


def unit(id: str, *after: str) -> Unit:
    return Unit(id=id, title=f"unit {id}", after=list(after))


def test_a_request_takes_its_coder_from_settings() -> None:
    request = AutocodeRequest(repo="/r", feature="csv-export", spec="Export as CSV.")

    assert request.provider == settings.autocode.provider
    assert request.model == settings.autocode.model
    assert request.review_model == settings.autocode.review_model


@pytest.mark.parametrize(
    "fields",
    [
        {"repo": "relative/repo", "feature": "x", "spec": "s"},
        {"repo": "/r", "feature": "Bad Slug", "spec": "s"},
        {"repo": "/r", "feature": "1st", "spec": "s"},
        {"repo": "/r", "feature": "x", "spec": "   "},
    ],
)
def test_a_bad_request_is_refused(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        AutocodeRequest(**fields)


def test_a_spec_is_a_file_only_when_it_is_one_absolute_path() -> None:
    assert AutocodeRequest(repo="/r", feature="x", spec="/specs/a.md").spec_is_file
    assert not AutocodeRequest(repo="/r", feature="x", spec="Export as CSV.").spec_is_file
    assert not AutocodeRequest(repo="/r", feature="x", spec="/a.md\nmore").spec_is_file


def test_units_in_build_order_are_taken() -> None:
    requirements = Requirements(
        units=[unit("M1"), unit("R1", "M1"), unit("R2", "M1", "R1")], parallel=True
    )

    assert requirements.ids == ["M1", "R1", "R2"]


@pytest.mark.parametrize(
    ("units", "problem"),
    [
        ([unit("R1"), unit("R1")], "used 2 times"),
        ([unit("R1", "M9")], "names no unit"),
        ([unit("R1", "R2"), unit("R2")], "does not come earlier"),
        ([unit("R1", "R1")], "does not come earlier"),
        ([unit("M1")], "no R unit"),
        ([unit("R1"), unit("M1")], "shared modules come before requirements"),
    ],
)
def test_units_that_cannot_be_built_are_refused(units: list[Unit], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        Requirements(units=units, parallel=False)


@pytest.mark.parametrize("id", ["X1", "R", "r1", "R1a"])
def test_a_unit_id_is_an_m_or_r_and_a_number(id: str) -> None:
    with pytest.raises(ValidationError):
        Unit(id=id, title="t", after=[])


def test_the_schemas_the_coder_sees_carry_the_rules_jsonschema_can_check() -> None:
    units = Requirements.model_json_schema()["properties"]["units"]

    assert units["minItems"] == 1
    assert units["contains"] == {"properties": {"id": {"pattern": "^R"}}}
    assert Requirements.model_json_schema()["additionalProperties"] is False
    assert Commands.model_json_schema()["properties"]["test"]["minLength"] == 1
