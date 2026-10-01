"""What the autocode workflow passes around: the request that starts it, what
the requirements, baseline and review jobs submit, the commits and command
runs code makes, and the result the workflow returns."""

from collections import Counter
from pathlib import PurePosixPath
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from autocode.settings.load import settings

FEATURE_PATTERN = r"^[a-z][a-z0-9_-]*$"  # a feature slug: the docs/tests folder and branch tail
UNIT_PATTERN = r"^[MR][0-9]+$"  # a unit id: M<n> a shared module, R<n> a requirement
MODULE = "M"  # the first letter of a shared module's id
REQUIREMENT = "R"  # the first letter of a requirement's id


class AutocodeRequest(BaseModel):
    """One feature to build in a git repo, from its spec, on one coder."""

    repo: str = Field(description="Absolute path of the git repo to build the feature in.")
    feature: str = Field(pattern=FEATURE_PATTERN, description="Slug: docs/<feature>, tests/...")
    spec: str = Field(description="An absolute path of the spec file, or the spec text.")
    provider: str = Field(default_factory=lambda: settings.autocode.provider)
    model: str = Field(
        default_factory=lambda: settings.autocode.model,
        description="Every job's model but the review's; empty = the harness's default.",
    )
    review_model: str = Field(
        default_factory=lambda: settings.autocode.review_model,
        description="The review job's model; empty = the harness's default.",
    )

    @field_validator("repo")
    @classmethod
    def repo_is_absolute(cls, repo: str) -> str:
        """The runner's cwd is not the caller's, so the repo is named in full."""
        if not PurePosixPath(repo).is_absolute():
            raise ValueError(f"repo must be an absolute path, got {repo!r}")
        return repo

    @field_validator("spec")
    @classmethod
    def spec_is_given(cls, spec: str) -> str:
        """No spec, no feature."""
        if not spec.strip():
            raise ValueError("spec must be non-empty")
        return spec

    @property
    def spec_is_file(self) -> bool:
        """True when `spec` names a file (one absolute path), not the text itself."""
        return "\n" not in self.spec and PurePosixPath(self.spec.strip()).is_absolute()


class Unit(BaseModel):
    """One unit of work: a shared module (M<n>) or a requirement (R<n>)."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=UNIT_PATTERN, description="`M1`, `R2`: its heading in REQUIREMENTS.md.")
    title: str = Field(description="Its heading's name, a few words.")
    after: list[str] = Field(
        description="The ids of the units it builds on, each listed earlier; empty when none."
    )


class Requirements(BaseModel):
    """What the requirements job submits: the units in build order, and
    whether they may be implemented at once."""

    model_config = ConfigDict(extra="forbid")
    units: list[Unit] = Field(
        min_length=1,
        json_schema_extra={"contains": {"properties": {"id": {"pattern": f"^{REQUIREMENT}"}}}},
        description="Every M and R heading of REQUIREMENTS.md in build order: shared modules "
        "first, then requirements; a unit comes after every unit in its `after`.",
    )
    parallel: bool = Field(
        description="True only when the units touch separate files, so they can be built at once."
    )

    @model_validator(mode="after")
    def units_can_be_built(self) -> Self:
        """Ids unique, every `after` id known and earlier, at least one R, the M units first."""
        problems = unit_problems(self.units)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def ids(self) -> list[str]:
        return [unit.id for unit in self.units]


def unit_problems(units: list[Unit]) -> list[str]:
    """Every reason the units cannot be built in the order given; empty when they can."""
    return [
        *(f"unit id {id!r} is used {n} times" for id, n in Counter(_ids(units)).items() if n > 1),
        *_after_problems(units),
        *([] if any(u.id.startswith(REQUIREMENT) for u in units) else ["no R unit"]),
        *_module_order_problems(units),
    ]


def _ids(units: list[Unit]) -> list[str]:
    return [unit.id for unit in units]


def _after_problems(units: list[Unit]) -> list[str]:
    """An `after` id that names no unit, or one that comes at or after its own."""
    known = {unit.id for unit in units}
    earlier: set[str] = set()
    problems = []
    for unit in units:
        for id in unit.after:
            if id not in known:
                problems.append(f"{unit.id}: after {id!r} names no unit")
            elif id not in earlier:
                problems.append(f"{unit.id}: after {id!r} does not come earlier")
        earlier.add(unit.id)
    return problems


def _module_order_problems(units: list[Unit]) -> list[str]:
    """An M unit listed after an R unit."""
    first_requirement = next(
        (index for index, unit in enumerate(units) if unit.id.startswith(REQUIREMENT)), len(units)
    )
    return [
        f"{unit.id}: shared modules come before requirements"
        for unit in units[first_requirement:]
        if unit.id.startswith(MODULE)
    ]


class Commands(BaseModel):
    """What the baseline job submits: the repo's own commands, run from its root."""

    model_config = ConfigDict(extra="forbid")
    test: str = Field(
        min_length=1,
        description="Runs the full test suite with no argument (new tests under tests/ "
        "included), and only the paths given when test paths are appended: "
        "`uv run pytest -q`.",
    )
    test_dirs: list[str] = Field(
        description="The test folders that exist now, relative to the repo root: `tests/unit`."
    )
    lint: str = Field(description="The repo's lint command; empty when it has none.")
    typecheck: str = Field(description="The repo's type check command; empty when it has none.")


class Finding(BaseModel):
    """One thing the reviewer found wrong."""

    model_config = ConfigDict(extra="forbid")
    file: str = Field(description="The file, relative to the repo root, with a line when known.")
    problem: str = Field(description="What is wrong, against the spec, a requirement or a case.")
    fix: str = Field(description="What must change.")


class Findings(BaseModel):
    """What the review job submits."""

    model_config = ConfigDict(extra="forbid")
    code: list[Finding] = Field(
        description="Problems in the code, one each; a fix job gets them. Empty when it is right."
    )
    tests: list[Finding] = Field(
        description="Problems in a test, one each. Tests are locked, so these go to the human, "
        "never to a fix job."
    )


class Check(BaseModel):
    """One of the repo's commands code runs, named by what it checks."""

    name: str = Field(description="`R1 tests`, `lint`, `full suite`: how a failure is named.")
    command: str


class Ran(BaseModel):
    """One check run: its exit code and the tail of its output."""

    name: str
    command: str
    exit_code: int
    timed_out: bool = False
    tail: str = Field(default="", description="The last characters of stdout and stderr.")

    @property
    def green(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class Commit(BaseModel):
    """One commit made on the feature branch."""

    sha: str
    message: str


class Gate(BaseModel):
    """The final gate: its last runs and the fix jobs it took."""

    green: bool
    runs: list[Ran]
    fixes: int = 0


class Spend(BaseModel):
    """What the jobs cost, summed from the job outcomes that carry it."""

    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    jobs: int = 0
    unknown: int = Field(default=0, description="Jobs that reported no usage, or a partial one.")

    def __add__(self, other: "Spend") -> "Spend":
        return Spend(
            cost_usd=self.cost_usd + other.cost_usd,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            jobs=self.jobs + other.jobs,
            unknown=self.unknown + other.unknown,
        )


class Autocoded(BaseModel):
    """What the workflow returns: the branch the feature landed on and how."""

    repo: str
    branch: str
    commits: list[Commit]
    units: list[str]
    findings: int = Field(description="Code problems the review found, given to the fix job.")
    test_findings: list[Finding] = Field(
        description="Test problems the review found, left for the human: tests are locked."
    )
    spend: Spend
    gate: Gate
