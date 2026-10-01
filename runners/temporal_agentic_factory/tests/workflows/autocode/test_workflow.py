"""The autocode workflow, run to a result or to its failure: every job and
every git, command and file activity is faked, scripted by `World`, so the
tests read as the story of one run. Nothing touches a real repo."""

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from autocode.contract import Autocoded, AutocodeRequest, Commit, Ran
from autocode.settings.load import settings as autocode_settings
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.job.submission.ask import AskedJob, asked_job
from agentic_factory.job.submission.contract import Schema
from agentic_factory.job.submission.schema import submission_schema
from agentic_factory.job.submission.submit import Submitted
from agentic_factory.tokens import Tokens
from temporal_agentic_factory.workflows.autocode.activities import (
    BranchRequest,
    CheckRequest,
    CommitRequest,
    FolderRequest,
    PathsRequest,
)
from temporal_agentic_factory.workflows.autocode.workflow import AutocodeWorkflow
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.execute import TryResult
from temporal_agentic_factory.workflows.job.submission import SubmissionRequest
from temporal_agentic_factory.workflows.job.workflow import JobWorkflow
from tests.workers import running

FEATURE = "csv"
UNITS = [
    {"id": "M1", "title": "Writer", "after": []},
    {"id": "R1", "title": "Export rows", "after": ["M1"]},
    {"id": "R2", "title": "Export header", "after": []},
]
COMMANDS = {"test": "pytest -q", "test_dirs": ["tests"], "lint": "ruff check .", "typecheck": ""}
LOCKED = {"M1/test_m1.py": "a", "R1/test_r1.py": "b", "R2/test_r2.py": "c", "main/test_e2e.py": "d"}


@dataclass
class World:
    """What the fakes do in one test; each field's default is the happy path."""

    baseline_red: bool = False
    green_before: set[str] = field(default_factory=set)  # new test folders green at red
    jobs_to_green: dict[str, int] = field(default_factory=dict)  # unit: jobs until its tests pass
    tests_changed_by: str = ""  # the job after which a locked test changes
    verdicts: dict[str, Verdict] = field(default_factory=dict)  # job name: its verdict
    findings: list[dict[str, str]] = field(default_factory=list)  # code problems the review submits
    test_findings: list[dict[str, str]] = field(default_factory=list)  # test problems it submits
    lint_red_runs: int = 0  # gate runs whose lint fails
    bad_requirements: int = 0  # requirements submissions that break the build order
    parallel: bool = False  # what the requirements job says of the units
    jobs: list[Job] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=lambda: dict(LOCKED))
    schemas: dict[str, Schema | None] = field(default_factory=dict)


world = World()


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    """The session is named by its job, so a follow-up in it is seen by its name."""
    return f"session:{job.name}"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> TryResult:
    world.jobs.append(job)
    if job.name == world.tests_changed_by:
        world.hashes = {**world.hashes, "R1/test_r1.py": "changed"}
    result = JobResult(
        session_id=job.session_id, cost_usd=0.1, tokens=Tokens(input=10, output=5), usage_known=True
    )
    return TryResult(result=result, runner="r1")


@activity.defn(name="record_job")
async def fake_record(outcome: JobOutcome) -> None:
    return None


@activity.defn(name="ask_for_submission")
async def fake_ask(request: SubmissionRequest) -> AskedJob:
    job = request.job
    world.schemas[job.session_id] = request.output_schema
    return asked_job(job, submission_schema(request.output_schema), "af", harness_for(job.provider))


@activity.defn(name="read_submission")
async def fake_read(session_id: str) -> Submitted:
    """The last job in the session: its scripted verdict, and its output when asked for one."""
    name = next(job.name for job in reversed(world.jobs) if job.session_id == session_id)
    verdict = world.verdicts.get(name, Verdict.DONE)
    report = JobReport(
        task=name,
        done=["wrote it"],
        not_done=[] if verdict == Verdict.DONE else ["the scaffold of R2"],
        problems=[],
        verdict=verdict,
    )
    output = fake_output(name) if world.schemas.get(session_id) else None
    return Submitted(report=report, output=output)


def fake_output(name: str) -> dict[str, Any]:
    if name.startswith("requirements"):
        if world.bad_requirements:
            world.bad_requirements -= 1
            return {"units": list(reversed(UNITS)), "parallel": False}
        return {"units": UNITS, "parallel": world.parallel}
    if name == "baseline":
        return COMMANDS
    if name == "review":
        return {"code": world.findings, "tests": world.test_findings}
    raise AssertionError(f"no fake output for {name}")


@activity.defn(name="autocode_branch")
async def fake_branch(request: BranchRequest) -> str:
    return f"autocode/{request.feature}"


@activity.defn(name="autocode_commit")
async def fake_commit(request: CommitRequest) -> Commit | None:
    world.commits.append(request.message.removeprefix(f"autocode({FEATURE}): "))
    return Commit(sha=f"sha{len(world.commits)}", message=request.message)


@activity.defn(name="autocode_check")
async def fake_check(request: CheckRequest) -> Ran:
    """Green unless the world says otherwise for this check."""
    name = request.check.name
    world.checks.append(name)
    return Ran(name=name, command=request.check.command, exit_code=0 if green(name) else 1)


def green(name: str) -> bool:
    if name == "baseline":
        return not world.baseline_red
    if name.startswith("tests/"):
        return name.removesuffix(" tests") in world.green_before
    unit, _, kind = name.partition(" ")
    if kind == "tests" and unit in {item["id"] for item in UNITS}:
        built = sum(1 for job in world.jobs if job.name.startswith(f"implement/{unit}"))
        return built >= world.jobs_to_green.get(unit, 1)
    if name == "lint":
        runs = world.checks.count("lint")
        return runs > world.lint_red_runs
    return True


@activity.defn(name="autocode_missing_files")
async def fake_missing(request: PathsRequest) -> list[str]:
    return []


@activity.defn(name="autocode_folders_without_tests")
async def fake_without_tests(request: PathsRequest) -> list[str]:
    return []


@activity.defn(name="autocode_test_hashes")
async def fake_hashes(request: FolderRequest) -> dict[str, str]:
    return dict(world.hashes)


ACTIVITIES = [
    fake_session,
    fake_record,
    fake_ask,
    fake_read,
    fake_branch,
    fake_commit,
    fake_check,
    fake_missing,
    fake_without_tests,
    fake_hashes,
]


async def _run(**scripted: Any) -> Autocoded:
    vars(world).update(vars(World(**scripted)))  # the fakes read this one World
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    async with env:
        await search_attributes.add(
            env.client, "default", [key.name for key in search_attributes.KEYS]
        )
        queue = f"test-{uuid.uuid4()}"
        async with running(
            env.client, queue, [AutocodeWorkflow, JobWorkflow], ACTIVITIES, fake_job
        ):
            return await env.client.execute_workflow(
                AutocodeWorkflow.run,
                AutocodeRequest(repo="/repo", feature=FEATURE, spec="Export the rows as CSV."),
                id=f"autocode-{FEATURE}-{uuid.uuid4().hex[:4]}",
                task_queue=queue,
            )


async def _failure(**scripted: Any) -> ApplicationError:
    with pytest.raises(WorkflowFailureError) as raised:
        await _run(**scripted)
    cause = raised.value.cause
    assert isinstance(cause, ApplicationError)
    return cause


def names() -> list[str]:
    return [job.name for job in world.jobs]


async def test_the_main_path_commits_every_stage_in_order() -> None:
    result = await _run()

    assert world.commits == [
        "requirements",
        "failures",
        "scaffold",
        "tests",
        "M1",
        "R1",
        "R2",
        "align",
        "gate",
    ]
    assert [commit.message for commit in result.commits] == [
        f"autocode({FEATURE}): {stage}" for stage in world.commits
    ]
    assert result.branch == "autocode/csv" and result.units == ["M1", "R1", "R2"]
    assert result.gate.green and result.gate.fixes == 0 and result.findings == 0
    assert result.spend.jobs == len(world.jobs) == 15 and result.spend.unknown == 0


async def test_every_job_is_named_by_its_stage_and_the_review_has_its_own_model() -> None:
    await _run()

    assert names()[0] == "requirements"
    assert sorted(names()[1:4]) == ["failures/M1", "failures/R1", "failures/R2"]
    assert names()[4:6] == ["baseline", "scaffold"]
    assert sorted(names()[6:10]) == ["e2e", "tests/M1", "tests/R1", "tests/R2"]
    assert names()[10:] == ["implement/M1", "implement/R1", "implement/R2", "align", "review"]
    review = next(job for job in world.jobs if job.name == "review")
    assert review.model == autocode_settings.autocode.review_model
    assert all(job.workdir == "/repo" for job in world.jobs)


async def test_red_runs_the_old_tests_then_every_new_folder_before_any_code() -> None:
    await _run()

    first_implement = world.checks.index("M1 tests")
    assert world.checks[:first_implement] == [
        "baseline",
        "existing tests",
        "tests/csv/M1 tests",
        "tests/csv/R1 tests",
        "tests/csv/R2 tests",
        "tests/csv/main tests",
    ]


async def test_parallel_units_are_built_in_waves_after_the_shared_modules() -> None:
    result = await _run(parallel=True)

    implements = [name for name in names() if name.startswith("implement/")]
    assert implements[0] == "implement/M1"
    assert sorted(implements[1:]) == ["implement/R1", "implement/R2"]
    assert world.commits[4] == "M1" and sorted(world.commits[5:7]) == ["R1", "R2"]
    assert result.gate.green


async def test_a_red_baseline_fails_before_the_scaffold() -> None:
    cause = await _failure(baseline_red=True)

    assert cause.type == "BaselineRed" and "baseline red" in cause.message
    assert "scaffold" not in names()


async def test_a_folder_green_before_any_code_fails_at_red_naming_it() -> None:
    cause = await _failure(green_before={"tests/csv/R2"})

    assert cause.type == "TestsGreenBeforeCode" and "tests/csv/R2" in cause.message
    assert not any(name.startswith("implement") for name in names())


async def test_a_red_unit_is_fixed_in_its_own_session_until_green() -> None:
    result = await _run(jobs_to_green={"R1": 2})

    implement = next(job for job in world.jobs if job.name == "implement/R1")
    fix = next(job for job in world.jobs if job.name == "implement/R1/fix/1")
    assert fix.session_id == implement.session_id == "session:implement/R1"
    assert fix.try_offset > 0 and "exited 1" in fix.prompt
    assert "R1" in world.commits and result.gate.green


async def test_a_unit_still_red_after_every_fix_fails_naming_it() -> None:
    cause = await _failure(jobs_to_green={"R1": 99})

    attempts = autocode_settings.autocode.implement_attempts
    assert cause.type == "UnitRed" and cause.message.startswith("R1 still red")
    assert names().count("implement/R1") == 1
    assert sum(1 for name in names() if name.startswith("implement/R1/fix/")) == attempts
    assert "R1" not in world.commits


async def test_a_changed_test_fails_the_run_as_read_only() -> None:
    cause = await _failure(tests_changed_by="implement/M1")

    assert cause.type == "TestsChanged" and "tests are read-only" in cause.message
    assert "R1/test_r1.py changed" in cause.message and "M1" not in world.commits


async def test_a_job_not_done_fails_the_run_with_its_report() -> None:
    cause = await _failure(verdicts={"scaffold": Verdict.PARTIAL})

    assert cause.type == "JobNotDone" and cause.message.startswith("scaffold: verdict partial")
    assert "not done: the scaffold of R2" in cause.message
    assert "scaffold" not in world.commits


async def test_review_findings_go_to_a_fix_job_then_the_suite_and_a_commit() -> None:
    finding = {"file": "src/csv.py:3", "problem": "No header row.", "fix": "Write it."}
    result = await _run(findings=[finding])

    fix = next(job for job in world.jobs if job.name == "review-fix")
    assert "No header row." in fix.prompt and fix.session_id == "session:review-fix"
    assert world.commits[-3:] == ["align", "review", "gate"] and result.findings == 1


async def test_test_findings_go_to_the_result_and_never_to_a_fix_job() -> None:
    finding = {"file": "tests/x/R1/test_a.py:3", "problem": "Duplicates main.", "fix": "Drop it."}
    result = await _run(test_findings=[finding])

    assert not any(job.name == "review-fix" for job in world.jobs)
    assert result.findings == 0
    assert [item.file for item in result.test_findings] == [finding["file"]]


async def test_a_red_gate_gets_a_fix_job_then_passes() -> None:
    result = await _run(lint_red_runs=1)

    assert names()[-1] == "gate/fix/1" and "lint" in world.jobs[-1].prompt
    assert result.gate.green and result.gate.fixes == 1
    assert world.checks.count("lint") == 2 and world.commits[-1] == "gate"


async def test_a_gate_still_red_after_every_fix_fails() -> None:
    cause = await _failure(lint_red_runs=99)

    assert cause.type == "GateRed" and "lint" in cause.message
    assert names().count("gate/fix/1") == 1
    assert len([name for name in names() if name.startswith("gate/fix/")]) == (
        autocode_settings.autocode.gate_attempts
    )


async def test_requirements_that_break_the_build_order_go_back_to_the_job() -> None:
    result = await _run(bad_requirements=1)

    resubmit = next(job for job in world.jobs if job.name == "requirements/resubmit/1")
    assert resubmit.session_id == "session:requirements" and "come earlier" in resubmit.prompt
    assert result.units == ["M1", "R1", "R2"]


async def test_requirements_still_broken_after_every_resubmit_fail_the_run() -> None:
    cause = await _failure(bad_requirements=99)

    assert cause.type == "StructuredOutputInvalid" and cause.message.startswith("requirements")
    assert "failures/M1" not in names()
