"""The autocode workflow: a feature spec turned into tested, committed code
on a branch of a git repo. The contract, build order, test lock and prompts
are the `autocode` app's; this module orders them on Temporal, one small
function per stage. Code runs git, the tests, red/green and the lock; the
coders only write files, and every job's verdict must be `done`."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from autocode.contract import (
        Autocoded,
        AutocodeRequest,
        Check,
        Commands,
        Commit,
        Findings,
        Gate,
        Ran,
        Requirements,
        Spend,
        Unit,
    )
    from autocode.lock import lock_problems
    from autocode.order import waves
    from autocode.prompts.prompt import prompt
    from autocode.run import Autocode
    from autocode.settings.load import settings as autocode_settings
    from temporalio.exceptions import ApplicationError

    from agentic_factory.job.contract import Job
    from agentic_factory.job.outcome import JobOutcome, verdict_of
    from agentic_factory.job.report.contract import Verdict
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.autocode.activities import (
        BranchRequest,
        CheckRequest,
        CommitRequest,
        FolderRequest,
        PathsRequest,
        autocode_branch,
        autocode_check,
        autocode_commit,
        autocode_folders_without_tests,
        autocode_missing_files,
        autocode_test_hashes,
    )
    from temporal_agentic_factory.workflows.job.child import (
        run_job_or_fail,
        run_job_with_structured_output,
    )

Locked = dict[str, str]  # the sha256 of every file under tests/<feature>/, taken at red


@workflow.defn(name="autocode")
class AutocodeWorkflow:
    """One feature built in a git repo by jobs, on its own branch: the
    requirements, the failure cases, the repo's commands, the scaffold, the
    tests (proven red, then locked), the units (built in waves, each fixed
    in its own session until its tests are green), the align pass, a review
    with fresh eyes, and the gate. Each stage is committed. Fails, typed and
    final, where the chain cannot go on: a dirty tree, a job not `done`, a
    red baseline, a test green before its code, a unit still red, a changed
    test, a red gate. Every job is named (`requirements`, `failures/R2`,
    `implement/M1`) for the UI and the status line."""

    @workflow.run
    async def run(self, request: AutocodeRequest) -> Autocoded:
        run = await branched(Autocode(request=request))
        run = await requirements_written(run)
        run = await failures_written(run)
        run = await baseline_found(run)
        run = await scaffolded(run)
        run = await tests_written(run)
        locked = await proven_red(run)
        run = await implemented(run, locked)
        run = await aligned(run, locked)
        run = await reviewed(run, locked)
        gate, run = await gated(run, locked)
        status(f"done: {run.branch}, {len(run.commits)} commits")
        return run.outcome(gate)


async def branched(run: Autocode) -> Autocode:
    """The feature branch, from a clean tree: the run starts here."""
    status(f"branching {run.request.repo}")
    request = BranchRequest(
        repo=run.request.repo,
        feature=run.feature,
        timeout_sec=autocode_settings.autocode.git_timeout_sec,
    )
    branch = await activity_done(
        autocode_branch, request, autocode_settings.autocode.git_timeout_sec, "branch"
    )
    return run.model_copy(update={"branch": branch})


async def requirements_written(run: Autocode) -> Autocode:
    """REQUIREMENTS.md written and its units stated in build order; committed."""
    status("writing the requirements")
    job = autocode_job(run, "requirements", prompt("requirements", run))
    requirements, spend = await output_done(run, job, Requirements)
    run = run.model_copy(update={"requirements": requirements}).spent(spend)
    await files_there(run, [run.requirements_path], "requirements")
    return await committed(run, "requirements")


async def failures_written(run: Autocode) -> Autocode:
    """One failure-case file per unit, written all at once; committed."""
    units = run.requirements.units
    status(f"writing the failure cases of {len(units)} units")
    outcomes = await asyncio.gather(
        *(
            job_done(autocode_job(run, f"failures/{unit.id}", prompt("failures", run, unit)))
            for unit in units
        )
    )
    run = run.spent(sum((spend_of(outcome) for outcome in outcomes), Spend()))
    await files_there(run, [run.failures_path(unit.id) for unit in units], "failures")
    return await committed(run, "failures")


async def baseline_found(run: Autocode) -> Autocode:
    """The repo's commands, and its test suite green before anything is built."""
    status("finding the repo's commands")
    job = autocode_job(run, "baseline", prompt("baseline", run))
    commands, spend = await output_done(run, job, Commands)
    run = run.model_copy(update={"commands": commands}).spent(spend)
    baseline = await checked(run, Check(name="baseline", command=commands.test))
    if not baseline.green:
        raise failed(
            "BaselineRed", f"baseline red: the tests fail before any change\n{tail(baseline)}"
        )
    return run


async def scaffolded(run: Autocode) -> Autocode:
    """Every object the units need, empty; committed."""
    status("writing the scaffold")
    run = run.spent(
        spend_of(await job_done(autocode_job(run, "scaffold", prompt("scaffold", run))))
    )
    return await committed(run, "scaffold")


async def tests_written(run: Autocode) -> Autocode:
    """Every unit's tests and the end-to-end ones, written all at once; committed."""
    units = run.requirements.units
    status(f"writing the tests of {len(units)} units and the end-to-end ones")
    jobs = [autocode_job(run, f"tests/{unit.id}", prompt("tests", run, unit)) for unit in units]
    jobs.append(autocode_job(run, "e2e", prompt("e2e", run)))
    outcomes = await asyncio.gather(*(job_done(job) for job in jobs))
    run = run.spent(sum((spend_of(outcome) for outcome in outcomes), Spend()))
    empty = await activity_done(
        autocode_folders_without_tests,
        PathsRequest(repo=run.request.repo, paths=run.test_folders),
        settings.autocode_activity.files_timeout_sec,
        "tests",
    )
    if empty:
        raise failed("TestsMissing", f"no test file in: {', '.join(empty)}")
    return await committed(run, "tests")


async def proven_red(run: Autocode) -> Locked:
    """The tests there were still green, every new folder red before any
    code; then the feature's tests locked."""
    status("proving the new tests red")
    green, red = run.red_checks()
    for check in green:
        ran = await checked(run, check)
        if not ran.green:
            raise failed("BaselineRed", f"the tests there were fail now\n{tail(ran)}")
    already = [check.name for check in red if (await checked(run, check)).green]
    if already:
        raise failed("TestsGreenBeforeCode", f"green before any code: {', '.join(already)}")
    return await test_hashes(run)


async def implemented(run: Autocode, locked: Locked) -> Autocode:
    """Every unit built, the shared modules first, in the waves of the build
    order: at once within a wave when the units may be, else one at a time.
    The units of a wave share one work tree, so their commits take turns."""
    turn = asyncio.Lock()
    for wave in waves(run.requirements.units, run.requirements.parallel):
        status(f"implementing {', '.join(unit.id for unit in wave)}")
        built = await asyncio.gather(*(unit_built(run, unit, locked, turn) for unit in wave))
        for commit, spend in built:
            run = run.committed(commit).spent(spend)
    return run


async def unit_built(
    run: Autocode, unit: Unit, locked: Locked, turn: asyncio.Lock
) -> tuple[Commit | None, Spend]:
    """One unit implemented until its own tests are green: each red run is
    given to a fix job in the same session, up to `implement_attempts`
    fixes. The lock is checked after every job; green, it is committed."""
    job = autocode_job(run, f"implement/{unit.id}", prompt("implement", run, unit))
    outcome = await job_done(job)
    spend = spend_of(outcome)
    await lock_held(run, locked)
    ran = await checked(run, run.unit_check(unit.id))
    fixes = 0
    while not ran.green:
        if fixes == autocode_settings.autocode.implement_attempts:
            raise failed("UnitRed", f"{unit.id} still red after {fixes} fixes\n{tail(ran)}")
        fixes += 1
        text = prompt("implement_fix", run, unit, failing=[ran])
        outcome = await job_done(
            follow_up(job, outcome, f"implement/{unit.id}/fix/{fixes}", text, fixes)
        )
        spend += spend_of(outcome)
        await lock_held(run, locked)
        ran = await checked(run, run.unit_check(unit.id))
    async with turn:
        commit = await commit_of(run, unit.id)
    return commit, spend


async def aligned(run: Autocode, locked: Locked) -> Autocode:
    """What the scaffold left behind removed; the full suite green; committed."""
    status("aligning the code")
    run = run.spent(spend_of(await job_done(autocode_job(run, "align", prompt("align", run)))))
    await suite_green(run, locked, "align")
    return await committed(run, "align")


async def reviewed(run: Autocode, locked: Locked) -> Autocode:
    """A review in a fresh session, on the review model; what it finds goes
    to a fix job in a new session, then the suite again; committed."""
    status("reviewing the code")
    job = autocode_job(run, "review", prompt("review", run), model=run.request.review_model)
    findings, spend = await output_done(run, job, Findings)
    run = run.model_copy(update={"findings": len(findings.items)}).spent(spend)
    if not findings.items:
        return run
    status(f"fixing {len(findings.items)} review findings")
    text = prompt("review_fix", run, findings=findings.items)
    run = run.spent(spend_of(await job_done(autocode_job(run, "review-fix", text))))
    await suite_green(run, locked, "review fix")
    return await committed(run, "review")


async def gated(run: Autocode, locked: Locked) -> tuple[Gate, Autocode]:
    """Lint, type check and the full suite; red, a fix job in a new session
    and the gate again, up to `gate_attempts` fixes. Green, the last commit."""
    fixes = 0
    while True:
        status("gate" + (f" after {fixes} fixes" if fixes else ""))
        runs = [await checked(run, check) for check in run.gate_checks()]
        failing = [item for item in runs if not item.green]
        if not failing:
            return Gate(green=True, runs=runs, fixes=fixes), await committed(run, "gate")
        if fixes == autocode_settings.autocode.gate_attempts:
            names = ", ".join(item.name for item in failing)
            raise failed("GateRed", f"gate red after {fixes} fixes: {names}\n{tail(failing[0])}")
        fixes += 1
        text = prompt("gate_fix", run, failing=failing)
        run = run.spent(spend_of(await job_done(autocode_job(run, f"gate/fix/{fixes}", text))))
        await lock_held(run, locked)


async def suite_green(run: Autocode, locked: Locked, after: str) -> None:
    """The full suite and the feature's tests green, the lock held; else the run fails."""
    await lock_held(run, locked)
    for check in run.suite_checks():
        ran = await checked(run, check)
        if not ran.green:
            raise failed("SuiteRed", f"{ran.name} red after the {after}\n{tail(ran)}")


async def lock_held(run: Autocode, locked: Locked) -> None:
    """The feature's tests as they were locked; any change fails the run."""
    problems = lock_problems(locked, await test_hashes(run))
    if problems:
        raise failed("TestsChanged", f"tests are read-only: {'; '.join(problems)}")


def autocode_job(run: Autocode, name: str, text: str, model: str | None = None) -> Job:
    """A job in the repo on the run's coder; `model` for the review's own."""
    cfg = autocode_settings.autocode
    return Job(
        name=name,
        prompt=text,
        workdir=run.request.repo,
        provider=run.request.provider,
        model=run.request.model if model is None else model,
        timeout_sec=cfg.job_timeout_sec,
        stall_sec=cfg.job_stall_sec,
    )


def follow_up(job: Job, outcome: JobOutcome, name: str, text: str, number: int) -> Job:
    """Follow-up `number` (from 1) of a job, in its session: its tries stored
    after those of the job, its reminders and the follow-ups before it."""
    tries_per_job = (
        settings.job_workflow.submit_reminders + 1
    ) * settings.job_activity.max_attempts
    return job.model_copy(
        update={
            "name": name,
            "prompt": text,
            "session_id": outcome.session_id,
            "try_offset": number * tries_per_job,
        }
    )


async def job_done(job: Job, schema: dict[str, Any] | None = None) -> JobOutcome:
    """The job run, with its output when asked for one by `schema`, and its
    verdict `done`. A job that failed for good, never submitted its output,
    or was not done, fails the run with its typed error; the report's
    not-done items and problems go in the message."""
    outcome = await (
        run_job_or_fail(job) if schema is None else run_job_with_structured_output(job, schema)
    )
    verdict = verdict_of(outcome)
    if verdict != Verdict.DONE:
        raise failed("JobNotDone", f"{job.name}: verdict {verdict.value}{reported(outcome)}")
    return outcome


async def output_done[Output: BaseModel](
    run: Autocode, job: Job, output: type[Output]
) -> tuple[Output, Spend]:
    """`job_done` with its output checked by the `output` model, which holds
    rules the schema the coder submits against cannot (build order, unique
    ids). An output that breaks them goes back to the job, in its session,
    up to `resubmit_attempts` times; then it is the job's typed failure."""
    schema = output.model_json_schema()
    outcome = await job_done(job, schema)
    spend = spend_of(outcome)
    resubmits = 0
    while True:
        try:
            return output.model_validate(outcome.output), spend
        except ValidationError as error:
            if resubmits == autocode_settings.autocode.resubmit_attempts:
                raise failed("StructuredOutputInvalid", f"{job.name}: {error}") from error
            resubmits += 1
            problems = [str(item["msg"]) for item in error.errors()]
            name = f"{job.name}/resubmit/{resubmits}"
            again = follow_up(
                job, outcome, name, prompt("resubmit", run, problems=problems), resubmits
            )
            outcome = await job_done(again, schema)
            spend += spend_of(outcome)


def reported(outcome: JobOutcome) -> str:
    """The report's not-done items and problems, one line each, for a failure's message."""
    report = outcome.report
    if report is None:
        return ": no report"
    lines = [f"not done: {item}" for item in report.not_done]
    lines += [f"problem: {item}" for item in report.problems]
    return "".join(f"\n- {line}" for line in lines)


async def checked(run: Autocode, check: Check) -> Ran:
    """One of the repo's commands run from its root, red or green."""
    cfg = autocode_settings.autocode
    request = CheckRequest(
        repo=run.request.repo,
        check=check,
        timeout_sec=cfg.test_timeout_sec,
        tail_chars=cfg.output_tail_chars,
    )
    return await activity_done(autocode_check, request, cfg.test_timeout_sec, check.name)


async def files_there(run: Autocode, paths: list[str], stage: str) -> None:
    """Every file a stage's jobs were to write is there; else the run fails."""
    missing = await activity_done(
        autocode_missing_files,
        PathsRequest(repo=run.request.repo, paths=paths),
        settings.autocode_activity.files_timeout_sec,
        stage,
    )
    if missing:
        raise failed("FilesMissing", f"{stage}: not written: {', '.join(missing)}")


async def test_hashes(run: Autocode) -> Locked:
    return await activity_done(
        autocode_test_hashes,
        FolderRequest(repo=run.request.repo, folder=run.tests_dir),
        settings.autocode_activity.files_timeout_sec,
        "test lock",
    )


async def committed(run: Autocode, stage: str) -> Autocode:
    """The run with the stage's commit, when it changed anything."""
    return run.committed(await commit_of(run, stage))


async def commit_of(run: Autocode, stage: str) -> Commit | None:
    """Everything in the work tree committed as `autocode(<feature>): <stage>`;
    None when nothing changed."""
    timeout_sec = autocode_settings.autocode.git_timeout_sec
    request = CommitRequest(
        repo=run.request.repo,
        feature=run.feature,
        message=run.message(stage),
        timeout_sec=timeout_sec,
    )
    return await activity_done(autocode_commit, request, timeout_sec, f"commit {stage}")


async def activity_done[Result](
    activity: Callable[[Any], Awaitable[Result]], request: Any, timeout_sec: int, summary: str
) -> Result:
    """An autocode activity run with its own timeout plus the margin, and its retries."""
    cfg = settings.autocode_activity
    return await workflow.execute_activity(
        activity,
        request,
        start_to_close_timeout=timedelta(seconds=timeout_sec + cfg.close_margin_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        summary=summary,
    )


def spend_of(outcome: JobOutcome) -> Spend:
    """One job's cost and tokens as the app counts them; unknown when it has none."""
    result = outcome.result
    if result is None:
        return Spend(jobs=1, unknown=1)
    return Spend(
        cost_usd=result.cost_usd,
        input_tokens=result.tokens.input,
        output_tokens=result.tokens.output,
        jobs=1,
        unknown=0 if result.usage_known else 1,
    )


def tail(ran: Ran) -> str:
    """A run's command, how it ended and its output's tail, for a failure's message."""
    ended = "timed out" if ran.timed_out else f"exited {ran.exit_code}"
    return f"`{ran.command}` {ended}:\n{ran.tail}"


def failed(kind: str, message: str) -> ApplicationError:
    """The typed, final error the run stops on."""
    return ApplicationError(message, type=kind, non_retryable=True)


def status(line: str) -> None:
    """The run's status line, shown on its page in the UI: where the chain is now."""
    workflow.set_current_details(line)
