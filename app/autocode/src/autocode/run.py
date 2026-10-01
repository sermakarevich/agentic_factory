"""One autocode run: where its docs and tests land in the repo, the checks
each stage runs, and the state the workflow grows as the stages finish."""

from pathlib import Path

from pydantic import BaseModel, Field

from autocode.contract import (
    Autocoded,
    AutocodeRequest,
    Check,
    Commands,
    Commit,
    Gate,
    Requirements,
    Spend,
    Unit,
)

DOCS = "docs"  # the repo folder the feature's docs land in: docs/<feature>/
TESTS = "tests"  # the repo folder the feature's tests land in: tests/<feature>/
REQUIREMENTS = "REQUIREMENTS.md"  # the requirements job's file in docs/<feature>/
FAILURES = "failures"  # the folder of one failure-case file per unit in docs/<feature>/
E2E = "main"  # the end-to-end tests' folder in tests/<feature>/


class Autocode(BaseModel):
    """The run so far: the request, then the branch, the units, the repo's
    commands, the commits and what the jobs cost as each stage fills them in."""

    request: AutocodeRequest
    branch: str = ""
    requirements: Requirements = Field(
        default_factory=lambda: Requirements.model_construct(units=[], parallel=False)
    )
    commands: Commands = Field(
        default_factory=lambda: Commands.model_construct(
            test="", test_dirs=[], lint="", typecheck=""
        )
    )
    commits: list[Commit] = []
    findings: int = 0
    spend: Spend = Field(default_factory=Spend)

    @property
    def repo(self) -> Path:
        return Path(self.request.repo)

    @property
    def feature(self) -> str:
        return self.request.feature

    @property
    def docs_dir(self) -> str:
        return _joined(DOCS, self.feature)

    @property
    def requirements_path(self) -> str:
        return _joined(self.docs_dir, REQUIREMENTS)

    def failures_path(self, unit_id: str) -> str:
        return _joined(self.docs_dir, FAILURES, f"{unit_id}.md")

    @property
    def tests_dir(self) -> str:
        return _joined(TESTS, self.feature)

    def tests_of(self, unit_id: str) -> str:
        """tests/<feature>/<id>: a unit's tests, or the end-to-end ones for `main`."""
        return _joined(self.tests_dir, unit_id)

    @property
    def test_folders(self) -> list[str]:
        """Every new test folder: one per unit, then the end-to-end one."""
        return [self.tests_of(id) for id in [*self.requirements.ids, E2E]]

    def unit_check(self, unit_id: str) -> Check:
        """A unit's own tests, run with the tests there were before it."""
        return self._test_check(
            f"{unit_id} tests", [*self.commands.test_dirs, self.tests_of(unit_id)]
        )

    def red_checks(self) -> tuple[list[Check], list[Check]]:
        """What the red stage runs: the tests there were, which must be
        green (none when the repo had no test folder), and each new folder,
        which must be red before any code is written."""
        existing = self.commands.test_dirs
        green = [self._test_check("existing tests", existing)] if existing else []
        return green, [
            self._test_check(f"{folder} tests", [folder]) for folder in self.test_folders
        ]

    def suite_checks(self) -> list[Check]:
        """The full suite, and the feature's tests by name in case the suite does not find them."""
        return [
            Check(name="full suite", command=self.commands.test),
            self._test_check("feature tests", [self.tests_dir]),
        ]

    def gate_checks(self) -> list[Check]:
        """What the gate runs: lint and type check when the repo has them, then the suites."""
        named = [("lint", self.commands.lint), ("typecheck", self.commands.typecheck)]
        return [
            *(Check(name=name, command=command) for name, command in named if command.strip()),
            *self.suite_checks(),
        ]

    def unit(self, unit_id: str) -> Unit:
        return next(unit for unit in self.requirements.units if unit.id == unit_id)

    def message(self, stage: str) -> str:
        """The commit message of a stage: `autocode(<feature>): <stage>`."""
        return f"autocode({self.feature}): {stage}"

    def committed(self, commit: Commit | None) -> "Autocode":
        """The run with `commit` added; the same run when nothing was committed."""
        if commit is None:
            return self
        return self.model_copy(update={"commits": [*self.commits, commit]})

    def spent(self, spend: Spend) -> "Autocode":
        return self.model_copy(update={"spend": self.spend + spend})

    def outcome(self, gate: Gate) -> Autocoded:
        """What the workflow returns."""
        return Autocoded(
            repo=self.request.repo,
            branch=self.branch,
            commits=self.commits,
            units=self.requirements.ids,
            findings=self.findings,
            spend=self.spend,
            gate=gate,
        )

    def _test_check(self, name: str, paths: list[str]) -> Check:
        return Check(name=name, command=" ".join([self.commands.test, *paths]))


def _joined(*parts: str) -> str:
    """A path relative to the repo root, as the coders and the commands see it."""
    return Path(*parts).as_posix()
