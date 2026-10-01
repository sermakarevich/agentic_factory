"""Where a run's files land, and the checks each stage runs."""

from autocode.contract import AutocodeRequest, Commands, Commit, Requirements, Unit
from autocode.run import Autocode

RUN = Autocode(
    request=AutocodeRequest(repo="/repo", feature="csv", spec="Export as CSV."),
    branch="autocode/csv",
    requirements=Requirements(
        units=[Unit(id="M1", title="m", after=[]), Unit(id="R1", title="r", after=["M1"])],
        parallel=False,
    ),
    commands=Commands(
        test="uv run pytest -q", test_dirs=["tests/unit"], lint="ruff check .", typecheck=""
    ),
)


def test_the_docs_and_tests_land_in_the_features_folders() -> None:
    assert RUN.requirements_path == "docs/csv/REQUIREMENTS.md"
    assert RUN.failures_path("R1") == "docs/csv/failures/R1.md"
    assert RUN.test_folders == ["tests/csv/M1", "tests/csv/R1", "tests/csv/main"]


def test_a_units_tests_run_with_the_tests_there_were() -> None:
    assert RUN.unit_check("R1").command == "uv run pytest -q tests/unit tests/csv/R1"


def test_red_runs_the_old_tests_and_each_new_folder_alone() -> None:
    green, red = RUN.red_checks()

    assert [check.command for check in green] == ["uv run pytest -q tests/unit"]
    assert [check.command for check in red] == [
        "uv run pytest -q tests/csv/M1",
        "uv run pytest -q tests/csv/R1",
        "uv run pytest -q tests/csv/main",
    ]


def test_red_has_no_old_tests_to_run_when_there_were_none() -> None:
    commands = RUN.commands.model_copy(update={"test_dirs": []})

    assert RUN.model_copy(update={"commands": commands}).red_checks()[0] == []


def test_the_gate_skips_a_command_the_repo_does_not_have() -> None:
    assert [check.name for check in RUN.gate_checks()] == ["lint", "full suite", "feature tests"]


def test_nothing_committed_leaves_the_commits_as_they_were() -> None:
    commit = Commit(sha="abc", message=RUN.message("requirements"))

    assert RUN.committed(None).commits == []
    assert RUN.committed(commit).commits == [commit]
    assert commit.message == "autocode(csv): requirements"
