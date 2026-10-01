import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from factory_settings.vault import workdir
    from pydantic import BaseModel
    from temporalio.exceptions import ApplicationError

    from agentic_factory.job.contract import Job
    from distill.contract import DistillRequest, EntryPlan, FetchedSource, FiledEntry
    from distill.fetch import work_dir_for
    from distill.prompts import Entry, index_prompt, page_prompt, plan_prompt, wiki_prompt
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.distill.activities import (
        FetchRequest,
        fetch_source,
        verify_entry,
    )
    from temporal_agentic_factory.workflows.job.child import run_job_or_fail
    from temporal_agentic_factory.workflows.structured_output.child import (
        run_job_with_structured_output,
    )

RUN_DATE_FORMAT = "%Y-%m-%d"

READER_STAGES = (
    ("digest and summary", ("digest", "summary")),
    ("reader's aids", ("explainer", "questions", "critical_thinking")),
)


class DistilledEntry(BaseModel):
    """Entry folder, the plan its jobs stated, and the fetched source."""

    path: str
    plan: EntryPlan
    fetched: FetchedSource


@workflow.defn(name="distill")
class DistillWorkflow:
    """Fetch one source, then jobs write its entry in the knowledge base."""

    @workflow.run
    async def run(self, request: DistillRequest) -> DistilledEntry:
        run_date = workflow.now().strftime(RUN_DATE_FORMAT)
        fetched = await _fetched(request, workflow.info().workflow_id)
        plan = await _planned(request, fetched, run_date)
        entry = Entry(request=request, fetched=fetched, plan=plan, run_date=run_date)
        await _written(
            "wiki pages",
            {f"wiki/{chunk.index}": wiki_prompt(entry, chunk) for chunk in fetched.chunks},
        )
        for stage, names in READER_STAGES:
            await _written(stage, {name: page_prompt(name, entry) for name in names})
        await _index_written_and_verified(entry)
        path = await _filed_path(entry)
        _status(f"done: {path}")
        return DistilledEntry(path=path, plan=plan, fetched=fetched)


def distill_job(name: str, prompt: str) -> Job:
    """Distill job with the workflow coder, model and limits, in the vault."""
    cfg = settings.distill_workflow
    return Job(
        name=name,
        prompt=prompt,
        workdir=str(workdir()),
        provider=cfg.provider,
        model=cfg.model,
        timeout_sec=cfg.job_timeout_sec,
        stall_sec=cfg.job_stall_sec,
    )


async def _fetched(request: DistillRequest, run_id: str) -> FetchedSource:
    """Source fetched under this run's work dir."""
    _status(f"fetching {request.url}")
    cfg = settings.fetch_activity
    return await workflow.execute_activity(
        fetch_source,
        FetchRequest(request=request, work_dir=str(work_dir_for(run_id))),
        start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        summary=request.url,
    )


async def _planned(request: DistillRequest, fetched: FetchedSource, run_date: str) -> EntryPlan:
    """Plan job stating where the entry lives."""
    _status(f"planning the entry for *{fetched.title}* ({len(fetched.chunks)} chunks)")
    done = await run_job_with_structured_output(
        distill_job("plan", plan_prompt(request, fetched, run_date)), EntryPlan.model_json_schema()
    )
    return EntryPlan.model_validate(done.structured_output)


async def _index_written_and_verified(entry: Entry) -> None:
    """Index job then verifier, until it passes or attempts run out."""
    attempts = settings.distill_workflow.index_attempts
    problems: list[str] = []
    for attempt in range(1, attempts + 1):
        await _written("index", {f"index/{attempt}": index_prompt(entry, problems)})
        _status(f"index: verifying, attempt {attempt} of {attempts}")
        problems = await _verified(entry.plan)
        if not problems:
            return
    raise ApplicationError(
        "the entry did not pass verification: " + "; ".join(problems),
        type="EntryNotVerified",
        non_retryable=True,
    )


async def _filed_path(entry: Entry) -> str:
    """Final folder: under the topic via the file job, else the plan folder."""
    if not entry.request.topic:
        return entry.plan.research_dir
    _status(f"filing the entry under {entry.request.topic}")
    done = await run_job_with_structured_output(
        distill_job("file", page_prompt("file", entry)), FiledEntry.model_json_schema()
    )
    return FiledEntry.model_validate(done.structured_output).path


async def _written(stage: str, pages: dict[str, str]) -> None:
    """Every page's job at once; the status line counts them in as they finish."""
    written: list[str] = []
    _status(_progress(stage, written, pages))
    await asyncio.gather(
        *(
            _written_and_counted(stage, name, prompt, written, pages)
            for name, prompt in pages.items()
        )
    )


async def _written_and_counted(
    stage: str, name: str, prompt: str, written: list[str], pages: dict[str, str]
) -> None:
    """One job of a stage, then the status line with it counted in."""
    await run_job_or_fail(distill_job(name, prompt))
    written.append(name)
    _status(_progress(stage, written, pages))


def _progress(stage: str, written: list[str], pages: dict[str, str]) -> str:
    """`wiki pages: 3 of 9 written; running: wiki/4, wiki/5`."""
    running = ", ".join(name for name in pages if name not in written)
    return f"{stage}: {len(written)} of {len(pages)} written; running: {running or 'none'}"


async def _verified(plan: EntryPlan) -> list[str]:
    """Verifier problems for the entry folder, none when it passes."""
    cfg = settings.verify_activity
    return await workflow.execute_activity(
        verify_entry,
        plan.research_dir,
        start_to_close_timeout=timedelta(seconds=cfg.timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        summary=plan.slug,
    )


def _status(line: str) -> None:
    """Status line on the run's page in the UI."""
    workflow.set_current_details(line)
