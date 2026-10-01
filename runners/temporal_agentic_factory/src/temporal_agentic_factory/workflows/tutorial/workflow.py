"""The tutorial workflow: a topic turned into a numbered tutorial in the
knowledge base. The contract, prompts, plan checks and review rounds are the
`tutorial` app's; this module orders them on Temporal, one small function per
stage."""

import asyncio
from datetime import timedelta

from pydantic import BaseModel, ValidationError
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from factory_settings.vault import workdir
    from temporalio.exceptions import ApplicationError
    from tutorial.contract import (
        Chapter,
        ChapterOutcome,
        ChapterStatus,
        Coder,
        Finished,
        Named,
        Review,
        Spend,
        TutorialOutcome,
        TutorialPlan,
        TutorialRequest,
    )
    from tutorial.plan import plan_problems
    from tutorial.prompts.prompt import prompt
    from tutorial.review import Next, after_review
    from tutorial.run import Tutorial, tutorials_dir
    from tutorial.settings.load import settings as tutorial_settings
    from tutorial.settings.model import CoderSettings

    from agentic_factory.job.contract import Job
    from agentic_factory.job.outcome import JobOutcome
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.job.child import (
        run_job_with_report,
        run_job_with_structured_output,
    )
    from temporal_agentic_factory.workflows.tutorial.activities import locate_tutorial


@workflow.defn(name="tutorial")
class TutorialWorkflow:
    """One topic, written up as a tutorial by jobs in the knowledge-base repo:
    named (when the request names no folder), located, designed, every
    chapter written and reviewed at once, then finished. Fails where the
    chain cannot go on (a folder in use, a plan that cannot be built, a
    designer or finish job that failed for good); a chapter that keeps failing
    its review is marked failed and the others carry on. Every job is named
    (`design`, `write/01`, `review/01/1`) for the UI and the status line."""

    @workflow.run
    async def run(self, request: TutorialRequest) -> TutorialOutcome:
        tutorial = Tutorial(request=request, root=str(tutorials_dir()))
        tutorial = await named(tutorial)
        tutorial = await located(tutorial)
        tutorial = await designed(tutorial)
        tutorial = await chapters_written(tutorial)
        finished, tutorial = await finished_tutorial(tutorial)
        status(f"done: {finished.index_path}")
        return tutorial.outcome(finished)


def tutorial_job(name: str, text: str, coder: Coder, timeout_sec: int, stall_sec: int) -> Job:
    """A tutorial job in the knowledge-base repo, on the role's coder."""
    return Job(
        name=name,
        prompt=text,
        workdir=str(workdir()),
        provider=coder.provider,
        model=coder.model,
        timeout_sec=timeout_sec,
        stall_sec=stall_sec,
    )


def role_job(name: str, text: str, coder: Coder, limits: CoderSettings) -> Job:
    """A job with the limits of its role's settings table."""
    return tutorial_job(name, text, coder, limits.timeout_sec, limits.stall_sec)


async def named(tutorial: Tutorial) -> Tutorial:
    """The folder name: the request's, else the one the naming job picks."""
    if tutorial.request.name:
        return tutorial
    status("naming the tutorial")
    designer = tutorial_settings.designer
    job = tutorial_job(
        "name",
        prompt("name", tutorial),
        tutorial.request.designer,
        tutorial_settings.tutorial.naming_timeout_sec,
        designer.stall_sec,
    )
    picked, spend = await stated(job, Named)
    return tutorial.named(picked.name).model_copy(update={"spend": tutorial.spend + spend})


async def located(tutorial: Tutorial) -> Tutorial:
    """The tutorial's folder made, refused when it is in use: the run starts here."""
    status(f"locating {tutorial.folder}")
    cfg = settings.tutorial_locate_activity
    await workflow.execute_activity(
        locate_tutorial,
        str(tutorial.folder),
        start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        summary=tutorial.request.name,
    )
    return tutorial


async def designed(tutorial: Tutorial) -> Tutorial:
    """The design job writes the plan and the specs and states the plan;
    a plan that cannot be built stops the run before any writer starts."""
    status("designing the tutorial")
    job = role_job(
        "design",
        prompt("design", tutorial),
        tutorial.request.designer,
        tutorial_settings.designer,
    )
    plan, spend = await stated(job, TutorialPlan)
    problems = plan_problems(plan, tutorial.request.formats)
    if problems:
        raise ApplicationError(
            f"the plan cannot be built: {'; '.join(problems)}", type="BadPlan", non_retryable=True
        )
    return tutorial.model_copy(update={"plan": plan, "spend": tutorial.spend + spend})


async def chapters_written(tutorial: Tutorial) -> Tutorial:
    """Every chapter written and reviewed at once (the provider limits queue
    the jobs); the status line counts them in as they finish."""
    chapters = tutorial.plan.chapters
    ended: list[ChapterOutcome] = []

    def progress() -> str:
        running = ", ".join(
            item.label for item in chapters if item.number not in {o.number for o in ended}
        )
        failed = sum(1 for item in ended if item.status == ChapterStatus.failed)
        return (
            f"chapters: {len(ended)} of {len(chapters)} ended, {failed} failed;"
            f" running: {running or 'none'}"
        )

    async def one(chapter: Chapter) -> ChapterOutcome:
        outcome = await chapter_done(tutorial, chapter)
        ended.append(outcome)
        status(progress())
        return outcome

    status(progress())
    outcomes = list(await asyncio.gather(*(one(chapter) for chapter in chapters)))
    spend = sum((item.spend for item in outcomes), tutorial.spend)
    return tutorial.model_copy(update={"chapters": outcomes, "spend": spend})


async def chapter_done(tutorial: Tutorial, chapter: Chapter) -> ChapterOutcome:
    """One chapter written, then reviewed; rewritten with the reviewer's
    problems while the request's rounds last; done or failed at the end."""
    rewrites = 0
    review, spend = await chapter_round(tutorial, chapter, rewrites, [])
    step = after_review(review, rewrites, tutorial.request.review_rounds)
    while step == Next.rewrite:
        rewrites += 1
        review, more = await chapter_round(tutorial, chapter, rewrites, review.problems)
        spend += more
        step = after_review(review, rewrites, tutorial.request.review_rounds)
    return ChapterOutcome(
        number=chapter.number,
        slug=chapter.slug,
        title=chapter.title,
        status=ChapterStatus.done if step == Next.done else ChapterStatus.failed,
        rewrites=rewrites,
        problems=review.problems if step == Next.failed else [],
        spend=spend,
    )


async def chapter_round(
    tutorial: Tutorial, chapter: Chapter, rewrites: int, problems: list[str]
) -> tuple[Review, Spend]:
    """One write (or rewrite, given the problems) and the review after it. A
    writer that failed for good is a failed review: the next round retries it."""
    outcome = await run_job_with_report(writer_job(tutorial, chapter, rewrites, problems))
    spend = spend_of(outcome)
    if outcome.result is None:
        return Review(passed=False, problems=[f"the writer job failed: {outcome.failure}"]), spend
    review, more = await reviewed(tutorial, chapter, rewrites)
    return review, spend + more


def writer_job(tutorial: Tutorial, chapter: Chapter, rewrites: int, problems: list[str]) -> Job:
    """`write/01` first, then `rewrite/01/<round>` with the reviewer's problems."""
    name = f"write/{chapter.label}" if not rewrites else f"rewrite/{chapter.label}/{rewrites}"
    text = (
        prompt("write", tutorial, chapter)
        if not rewrites
        else prompt("rewrite", tutorial, chapter, problems)
    )
    return role_job(name, text, tutorial.request.writer, tutorial_settings.writer)


async def reviewed(tutorial: Tutorial, chapter: Chapter, rewrites: int) -> tuple[Review, Spend]:
    """The review job's verdict, `review/01` then `review/01/<round>`. A
    review job that failed for good, or stated nothing, is a failed review
    with that reason; a cancellation is raised."""
    name = f"review/{chapter.label}" + (f"/{rewrites}" if rewrites else "")
    job = role_job(
        name,
        prompt("review", tutorial, chapter),
        tutorial.request.reviewer,
        tutorial_settings.reviewer,
    )
    try:
        return await stated(job, Review)
    except ApplicationError as error:
        return Review(passed=False, problems=[f"the review job failed: {error.message}"]), Spend(
            jobs=1, unknown=1
        )


async def finished_tutorial(tutorial: Tutorial) -> tuple[Finished, Tutorial]:
    """The finish job: one pass over the whole tutorial, its index and its
    line in the tutorials' index."""
    status("finishing: consistency pass and index")
    designer = tutorial_settings.designer
    job = tutorial_job(
        "finish",
        prompt("finish", tutorial),
        tutorial.request.designer,
        tutorial_settings.tutorial.finish_timeout_sec,
        designer.stall_sec,
    )
    finished, spend = await stated(job, Finished)
    return finished, tutorial.model_copy(update={"spend": tutorial.spend + spend})


async def stated[Output: BaseModel](job: Job, output: type[Output]) -> tuple[Output, Spend]:
    """The job run, what it stated as the `output` model, and what it cost.
    A statement that does not fit the model is the job's typed failure."""
    done = await run_job_with_structured_output(job, output.model_json_schema())
    try:
        stated_output = output.model_validate(done.output)
    except ValidationError as error:
        raise ApplicationError(
            f"{job.name}: {error}", type="StructuredOutputInvalid", non_retryable=True
        ) from error
    return stated_output, spend_of(done)


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


def status(line: str) -> None:
    """The run's status line, shown on its page in the UI: where the chain is now."""
    workflow.set_current_details(line)
