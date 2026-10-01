"""Every template renders from one run's state with no placeholder left,
with the rules pasted in."""

import pytest

from autocode.contract import (
    AutocodeRequest,
    Commands,
    Finding,
    Ran,
    Requirements,
    Unit,
)
from autocode.prompts.prompt import FOLDER, prompt
from autocode.run import Autocode

UNIT = Unit(id="R1", title="Export rows", after=["M1"])
RUN = Autocode(
    request=AutocodeRequest(repo="/repo", feature="csv", spec="Export the rows as CSV."),
    branch="autocode/csv",
    requirements=Requirements(
        units=[Unit(id="M1", title="Writer", after=[]), UNIT], parallel=False
    ),
    commands=Commands(test="uv run pytest -q", test_dirs=["tests"], lint="", typecheck=""),
)
FAILING = [
    Ran(name="R1 tests", command="uv run pytest -q tests/csv/R1", exit_code=1, tail="E boom")
]
FINDINGS = [Finding(file="src/csv.py:3", problem="No header row.", fix="Write the header.")]
NAMES = sorted(path.stem for path in FOLDER.glob("*.md"))


def test_every_job_has_a_template() -> None:
    assert NAMES == [
        "align",
        "baseline",
        "e2e",
        "failures",
        "gate_fix",
        "implement",
        "implement_fix",
        "requirements",
        "resubmit",
        "review",
        "review_fix",
        "rules",
        "scaffold",
        "tests",
    ]


@pytest.mark.parametrize("name", NAMES)
def test_a_template_renders_with_no_placeholder_left(name: str) -> None:
    text = prompt(name, RUN, unit=UNIT, failing=FAILING, findings=FINDINGS, problems=["x"])

    assert "$" not in text


@pytest.mark.parametrize("name", [name for name in NAMES if name != "rules"])
def test_every_job_gets_the_rules(name: str) -> None:
    text = prompt(name, RUN, unit=UNIT)

    assert "Rules for every autocode job" in text
    assert "Tests are read-only after creation" in text


def test_a_unit_job_gets_its_files_and_its_limited_test_command() -> None:
    text = prompt("implement", RUN, unit=UNIT)

    assert "docs/csv/failures/R1.md" in text
    assert "tests/csv/R1/" in text
    assert "uv run pytest -q tests tests/csv/R1" in text
    assert "It builds on: M1." in text


def test_a_fix_gets_the_failing_output_and_the_findings() -> None:
    assert "exited 1" in prompt("implement_fix", RUN, unit=UNIT, failing=FAILING)
    assert "E boom" in prompt("gate_fix", RUN, failing=FAILING)
    assert "- `src/csv.py:3`: No header row. Fix: Write the header." in prompt(
        "review_fix", RUN, findings=FINDINGS
    )


def test_the_spec_is_pasted_or_pointed_to() -> None:
    assert "Export the rows as CSV." in prompt("requirements", RUN)
    request = RUN.request.model_copy(update={"spec": "/specs/csv.md"})
    pointed = prompt("requirements", RUN.model_copy(update={"request": request}))

    assert "the file `/specs/csv.md`" in pointed
