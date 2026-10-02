"""The research workflow: a focus question turned into a folder of digests.
The state, prompts and ranking are the `research` app's; this module orders
them on Temporal, one small function per stage."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from factory_settings.vault import workdir
    from research.contract import (
        Candidate,
        DiscoveredPath,
        IndexPath,
        PlannedSource,
        ResearchedTopic,
        ResearchPlan,
        ResearchRequest,
        SourceOutcome,
        SourceStatus,
    )
    from research.prompts.prompt import prompt
    from research.rank import judge_questions, ranked, scored
    from research.run import Research
    from research.settings.load import settings as research_settings
    from temporalio.exceptions import ApplicationError, ChildWorkflowError, is_cancelled_exception

    from agentic_factory.job.contract import Job
    from agentic_factory.step.judge.answer import Answer, CheckAnswer, ChoiceAnswer
    from agentic_factory.step.judge.contract import Judgment
    from distill.contract import DistillRequest
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.distill.name import source_name
    from temporal_agentic_factory.workflows.distill.workflow import DistillWorkflow, distill_job
    from temporal_agentic_factory.workflows.job import search_attributes
    from temporal_agentic_factory.workflows.job.child import (
        child_id,
        run_job_or_fail,
        run_job_with_structured_output,
    )
    from temporal_agentic_factory.workflows.judge.workflow import run_judgment
    from temporal_agentic_factory.workflows.research.activities import (
        locate_target,
        read_candidates,
    )

AGGREGATES = ("digest", "overview", "agreements", "disagreements", "open_questions")


@workflow.defn(name="research")
class ResearchWorkflow:
    """One focus question, written up by jobs and child distill runs in the
    knowledge-base repo. Fails where the chain cannot go on (a bad topic, a
    missing candidates file, a job that failed for good); a dead child distill
    run is a skipped ledger row instead. Every job is named (`discover`,
    `topic/01`, `lens/tech`) for the UI and the status line."""

    @workflow.run
    async def run(self, request: ResearchRequest) -> ResearchedTopic:
        research = await located(request)
        research = await discovered(research)
        research = await ranking(research)
        research = await assigned(research)
        research = await distilled(research)
        await written(
            "topic digests",
            {
                f"topic/{sub.nn}": prompt("topic", research, subtopic=sub)
                for sub in research.plan.subtopics
            },
        )
        await written("aggregates", {name: prompt(name, research) for name in AGGREGATES})
        await written(
            "lenses",
            {
                f"lens/{lens.lens}": prompt("lens", research, lens=lens)
                for lens in research.plan.lenses
            },
        )
        index = await indexed(research)
        status(f"done: {index.index_path}")
        return research.researched(index.index_path)


def research_job(name: str, text: str, planning: bool = False) -> Job:
    """A research job in the knowledge-base repo. Planning jobs (discover,
    assign) run on the stronger searching coder with longer to search the web."""
    cfg = settings.research_workflow
    return Job(
        name=name,
        prompt=text,
        workdir=str(workdir()),
        provider=cfg.planning_provider if planning else cfg.provider,
        model=cfg.planning_model if planning else cfg.model,
        timeout_sec=cfg.planning_timeout_sec if planning else cfg.job_timeout_sec,
        stall_sec=cfg.job_stall_sec,
    )


async def located(request: ResearchRequest) -> Research:
    """The run's folder made: the run starts here."""
    status(f"locating {request.topic}/research/{request.target}")
    cfg = settings.locate_activity
    target_dir = await activity_run(
        locate_target, request, cfg.timeout_sec, cfg.max_attempts, request.topic
    )
    return Research(request=request, target_dir=target_dir)


async def discovered(research: Research) -> Research:
    """The discover job states the candidates file; the file is read back."""
    status("discovering candidates")
    job = research_job("discover", prompt("discover", research), planning=True)
    path = (await stated(job, DiscoveredPath)).candidates_path
    cfg = settings.candidates_activity
    found = await activity_run(
        read_candidates, path, cfg.timeout_sec, cfg.max_attempts, Path(path).name
    )
    return research.model_copy(update={"candidates": found.candidates})


async def ranking(research: Research) -> Research:
    """One judgment per candidate not already in the knowledge base, all at
    once, then the app's order into shortlist, reserve and rejected."""
    to_judge = research.to_judge()
    status(f"ranking {len(to_judge)} candidates")
    answered = await asyncio.gather(*(judged(research, item) for item in to_judge))
    candidates = ranked(
        [*answered, *research.known()],
        research.request.n_sources,
        research_settings.research.reserve_share,
    )
    return research.model_copy(update={"candidates": candidates})


async def judged(research: Research, candidate: Candidate) -> Candidate:
    """The candidate with the judge's answers about it as scores."""
    judgment = Judgment.model_validate(
        {"state": candidate.model_dump(), "questions": judge_questions(research.request.focus)}
    )
    result = await run_judgment(judgment)
    answers = {name: plain_answer(answer) for name, answer in result.answers.items()}
    return scored(candidate, answers)


def plain_answer(answer: Answer) -> float | str:
    """A judge answer as the value the app reads: the label, the level, the probability."""
    if isinstance(answer, ChoiceAnswer):
        return answer.choice
    if isinstance(answer, CheckAnswer):
        return answer.yes
    return answer.score


async def assigned(research: Research) -> Research:
    """The assign job over the ranked rows states the plan."""
    status("assigning sources to sub-topics")
    job = research_job("assign", prompt("assign", research), planning=True)
    return research.model_copy(update={"plan": await stated(job, ResearchPlan)})


async def distilled(research: Research) -> Research:
    """One child distill run per fresh source, at most `sources_at_once`
    running: each one spends several coder slots."""
    fresh = research.plan.fresh
    status(f"distilling {len(fresh)} sources")
    slots = asyncio.Semaphore(settings.research_workflow.sources_at_once)

    async def with_slot(source: PlannedSource) -> SourceOutcome:
        async with slots:
            return await distill_one(research, source)

    outcomes = await asyncio.gather(*(with_slot(source) for source in fresh))
    return research.model_copy(update={"sources": list(outcomes)})


async def distill_one(research: Research, source: PlannedSource) -> SourceOutcome:
    """One child distill run, named by its url tail in the UI. A run that
    failed is a skipped ledger row with its reason, never a failed workflow;
    a cancelled one is raised."""
    status(f"distilling {source.key}: {source.title}")
    row = {"key": source.key, "url": source.url, "title": source.title}
    try:
        filed = await workflow.execute_child_workflow(
            DistillWorkflow.run,
            DistillRequest(
                url=source.url,
                topic=research.request.topic,
                research_target=research.target_dir,
                root=research.request.root,
            ),
            id=child_id(source.key),
            static_summary=f"{source.key}: {source.title}",
            search_attributes=search_attributes.at_start(
                distill_job("", ""), source_name(source.url)
            ),
            parent_close_policy=ParentClosePolicy.REQUEST_CANCEL,
        )
    except ChildWorkflowError as error:
        if is_cancelled_exception(error):
            raise
        reason = error.cause.message if isinstance(error.cause, ApplicationError) else str(error)
        return SourceOutcome(**row, status=SourceStatus.skipped, reason=reason)
    return SourceOutcome(**row, status=SourceStatus.succeeded, path=filed.path)


async def indexed(research: Research) -> IndexPath:
    """The index job states the hub index it wrote."""
    status("writing the index")
    return await stated(research_job("index", prompt("index", research)), IndexPath)


async def written(stage: str, prompts: dict[str, str]) -> None:
    """The jobs for `prompts` (job name to prompt), all at once; the status
    line counts them in as they finish: `lenses: 1 of 2 written; running: lens/ai`."""
    done: list[str] = []

    def progress() -> str:
        running = ", ".join(name for name in prompts if name not in done)
        return f"{stage}: {len(done)} of {len(prompts)} written; running: {running or 'none'}"

    async def one(name: str, text: str) -> None:
        await run_job_or_fail(research_job(name, text))
        done.append(name)
        status(progress())

    status(progress())
    await asyncio.gather(*(one(name, text) for name, text in prompts.items()))


async def stated[Output: BaseModel](job: Job, output: type[Output]) -> Output:
    """The job run, and what it stated as the `output` model."""
    done = await run_job_with_structured_output(job, output.model_json_schema())
    return output.model_validate(done.output)


async def activity_run[Result](
    fn: Callable[[Any], Awaitable[Result]],
    arg: object,
    timeout_sec: int,
    max_attempts: int,
    summary: str,
) -> Result:
    """An activity with its settings table's timeout and attempts."""
    return await workflow.execute_activity(
        fn,
        arg,
        start_to_close_timeout=timedelta(seconds=timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=max_attempts),
        summary=summary,
    )


def status(line: str) -> None:
    """The run's status line, shown on its page in the UI: where the chain is now."""
    workflow.set_current_details(line)
