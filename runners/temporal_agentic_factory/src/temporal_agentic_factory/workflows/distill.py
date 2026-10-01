"""The distill workflow: one source turned into a knowledge-base entry,
as fleet's summarise flow did it. The steps and their prompts are the
`distill` app's; this module only orders them on Temporal:

    fetch (activity)
    plan (job, states the entry folder)
    wiki pages (one job per chunk, all at once)
    digest + summary (two jobs at once)
    explainer + questions + critical thinking (three jobs at once)
    index (job), verified (activity); the verifier's problems go back to
        the index job until it passes or the attempts run out
    file under the topic (job, only when the request names one)
"""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel
    from temporalio.exceptions import ApplicationError

    from agentic_factory.job.contract import Job
    from distill.contract import DistillRequest, EntryPlan, FetchedSource, FiledEntry
    from distill.prompts.critical_thinking import critical_thinking_prompt
    from distill.prompts.digest import digest_prompt
    from distill.prompts.explainer import explainer_prompt
    from distill.prompts.file import file_prompt
    from distill.prompts.index import index_prompt
    from distill.prompts.plan import plan_prompt
    from distill.prompts.questions import questions_prompt
    from distill.prompts.summary import summary_prompt
    from distill.prompts.wiki import wiki_prompt
    from distill.vault import work_dir_for, workdir
    from temporal_agentic_factory.activities.distill import (
        FetchRequest,
        fetch_source,
        verify_entry,
    )
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.job import run_job_or_fail
    from temporal_agentic_factory.workflows.structured_output import (
        run_job_with_structured_output,
    )

RUN_DATE_FORMAT = "%Y-%m-%d"  # how the plan and summary prompts name today


class DistilledEntry(BaseModel):
    """What the workflow returns: the entry's final folder, the plan the
    jobs wrote it from, and the fetched source they read."""

    path: str
    plan: EntryPlan
    fetched: FetchedSource


@workflow.defn(name="distill")
class DistillWorkflow:
    """One source, fetched once and written up by a chain of jobs, all in the
    knowledge-base repo. Fails where the chain cannot go on: a source that
    cannot be fetched, a job that failed for good, an entry that never
    passed verification."""

    @workflow.run
    async def run(self, request: DistillRequest) -> DistilledEntry:
        run_date = workflow.now().strftime(RUN_DATE_FORMAT)
        fetched = await _fetched(request, workflow.info().workflow_id)
        plan = await _planned(request, fetched, run_date)
        await _wiki_pages_written(request, fetched, plan)
        await _digest_and_summary_written(request, fetched, plan, run_date)
        await _explainer_questions_and_critical_thinking_written(request, fetched, plan)
        await _index_written_and_verified(request, fetched, plan)
        path = await _filed_path(request, fetched, plan)
        return DistilledEntry(path=path, plan=plan, fetched=fetched)


def distill_job(prompt: str) -> Job:
    """A distill job: the workflow's coder and model, in the knowledge-base
    repo, with the workflow's limits."""
    cfg = settings.distill_workflow
    return Job(
        prompt=prompt,
        workdir=str(workdir()),
        provider=cfg.provider,
        model=cfg.model,
        timeout_sec=cfg.job_timeout_sec,
        stall_sec=cfg.job_stall_sec,
    )


async def _fetched(request: DistillRequest, run_id: str) -> FetchedSource:
    """The fetch activity, under this run's own work dir, with the fetch policy."""
    cfg = settings.fetch_activity
    return await workflow.execute_activity(
        fetch_source,
        FetchRequest(request=request, work_dir=str(work_dir_for(run_id))),
        start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
    )


async def _planned(request: DistillRequest, fetched: FetchedSource, run_date: str) -> EntryPlan:
    """The plan job, which states where the entry lives and what it is called."""
    job = distill_job(plan_prompt(request, fetched, run_date))
    done = await run_job_with_structured_output(job, EntryPlan.model_json_schema())
    return EntryPlan.model_validate(done.structured_output)


async def _wiki_pages_written(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan
) -> None:
    """One wiki job per chunk, all started at once."""
    await asyncio.gather(
        *(_done(wiki_prompt(request, fetched, plan, chunk)) for chunk in fetched.chunks)
    )


async def _digest_and_summary_written(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan, run_date: str
) -> None:
    """The digest and the summary, at once: both read only the wiki pages."""
    await asyncio.gather(
        _done(digest_prompt(request, fetched, plan)),
        _done(summary_prompt(request, fetched, plan, run_date)),
    )


async def _explainer_questions_and_critical_thinking_written(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan
) -> None:
    """The three reader's-aid pages, at once: each reads the summary and digest."""
    await asyncio.gather(
        _done(explainer_prompt(request, fetched, plan)),
        _done(questions_prompt(request, fetched, plan)),
        _done(critical_thinking_prompt(request, fetched, plan)),
    )


async def _index_written_and_verified(
    request: DistillRequest, fetched: FetchedSource, plan: EntryPlan
) -> None:
    """The index job, then the verifier; its problems go back into the next
    index job's prompt. Gives up after `index_attempts` runs."""
    problems: list[str] = []
    for _ in range(settings.distill_workflow.index_attempts):
        await _done(index_prompt(request, fetched, plan, problems))
        problems = await _verified(plan.research_dir)
        if not problems:
            return
    raise ApplicationError(
        "the entry did not pass verification: " + "; ".join(problems),
        type="EntryNotVerified",
        non_retryable=True,
    )


async def _filed_path(request: DistillRequest, fetched: FetchedSource, plan: EntryPlan) -> str:
    """The entry's final folder: moved under its topic by the file job when
    the request names one, else where the plan put it."""
    if not request.topic:
        return plan.research_dir
    job = distill_job(file_prompt(request, fetched, plan))
    done = await run_job_with_structured_output(job, FiledEntry.model_json_schema())
    return FiledEntry.model_validate(done.structured_output).path


async def _done(prompt: str) -> None:
    """A distill job with this prompt, run to a result or raising."""
    await run_job_or_fail(distill_job(prompt))


async def _verified(research_dir: str) -> list[str]:
    """The verify activity with the verify policy: the problems it found."""
    cfg = settings.verify_activity
    return await workflow.execute_activity(
        verify_entry,
        research_dir,
        start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
    )
