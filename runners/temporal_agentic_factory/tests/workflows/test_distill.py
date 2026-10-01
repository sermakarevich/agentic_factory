import json
import uuid
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from distill.contract import DistillRequest, EntryType, FetchedChunk, FetchedSource
from temporal_agentic_factory import search_attributes
from temporal_agentic_factory.activities.distill import FetchRequest
from temporal_agentic_factory.activities.job import TryResult
from temporal_agentic_factory.activities.report import ReportRequest
from temporal_agentic_factory.activities.structured_output import StructuredOutputRequest
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.distill import DistilledEntry, DistillWorkflow

RESEARCH_DIR = "/kb/knowledge/research/AThing"
PLAN = {"research_dir": RESEARCH_DIR, "slug": "AThing", "title": "A thing", "type": "Article"}
FILED = {"path": "/kb/knowledge/research_topics/agents/AThing"}
fetches: list[FetchRequest] = []
jobs: list[Job] = []
verified: list[str] = []


def _fetched(work_dir: str) -> FetchedSource:
    return FetchedSource(
        work_dir=work_dir,
        source_md=f"{work_dir}/source.md",
        title="A thing",
        kind="article",
        type=EntryType.article,
        fetched_at="2026-09-30T00:00:00+00:00",
        chunks=[
            FetchedChunk(
                index=i,
                slug=f"0{i}-part",
                title=f"Part {i}",
                path=f"{work_dir}/chunks/0{i}-part.md",
                chars=10,
            )
            for i in (1, 2)
        ],
    )


@activity.defn(name="fetch_source")
async def fake_fetch(request: FetchRequest) -> FetchedSource:
    fetches.append(request)
    return _fetched(request.work_dir)


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    return f"s{len(jobs)}"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> TryResult:
    jobs.append(job)
    return TryResult(result=JobResult(session_id=job.session_id, cost_usd=0.1), runner="r1")


@activity.defn(name="build_report")
async def fake_report(request: ReportRequest) -> JobReport:
    return JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.DONE)


@activity.defn(name="record_job")
async def fake_record(outcome: JobOutcome) -> None:
    return None


@activity.defn(name="extract_structured_output")
async def fake_extract(request: StructuredOutputRequest) -> dict[str, Any]:
    """The plan for the plan job's schema, the filed path for the file job's."""
    return PLAN if "research_dir" in request.output_schema["properties"] else FILED


@activity.defn(name="verify_entry")
async def verify_once_failing(research_dir: str) -> list[str]:
    verified.append(research_dir)
    return ["verify: missing digest.md"] if len(verified) == 1 else []


@activity.defn(name="verify_entry")
async def verify_always_failing(research_dir: str) -> list[str]:
    verified.append(research_dir)
    return ["verify: missing digest.md"]


async def _environment() -> WorkflowEnvironment:
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    await search_attributes.add(env.client, "default", [key.name for key in search_attributes.KEYS])
    return env


labels: list[tuple[str, str]] = []  # (activity type, summary) of every activity scheduled


async def _run(request: DistillRequest, verify: Any) -> DistilledEntry:
    fetches.clear()
    jobs.clear()
    verified.clear()
    labels.clear()
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[DistillWorkflow],
            activities=[
                fake_fetch,
                fake_session,
                fake_job,
                fake_report,
                fake_record,
                fake_extract,
                verify,
            ],
        ):
            handle = await env.client.start_workflow(
                DistillWorkflow.run,
                request,
                id=f"distill-{uuid.uuid4()}",
                task_queue=queue,
            )
            result = await handle.result()
            labels.extend(await _labels(handle))
            return result


async def _labels(handle: Any) -> list[tuple[str, str]]:
    """(activity type, summary) of every activity the run scheduled, from its history."""
    found = []
    for event in (await handle.fetch_history()).events:
        if event.HasField("activity_task_scheduled_event_attributes"):
            kind = event.activity_task_scheduled_event_attributes.activity_type.name
            summary = event.user_metadata.summary.data
            found.append((kind, json.loads(summary) if summary else ""))
    return found


def _prompts_mentioning(*words: str) -> list[str]:
    return [job.prompt for job in jobs if all(word in job.prompt for word in words)]


async def test_the_source_is_fetched_once_then_every_page_is_a_job() -> None:
    result = await _run(DistillRequest(url="https://example.org/a"), verify_once_failing)

    (fetch,) = fetches
    assert fetch.request.url == "https://example.org/a"
    assert fetch.work_dir.endswith(result.fetched.work_dir.rsplit("/", 1)[-1])
    assert result.path == RESEARCH_DIR and result.plan.slug == "AThing"
    # plan, 2 wiki, digest, summary, explainer, questions, critical thinking, index x2
    assert len(jobs) == 10
    assert len(_prompts_mentioning("chunks/01-part.md")) == 1
    assert len(_prompts_mentioning("chunks/02-part.md")) == 1
    assert len(_prompts_mentioning("index.md", "## Verifier problems")) == 1
    assert verified == [RESEARCH_DIR, RESEARCH_DIR]


async def test_every_job_runs_in_the_vault_with_the_workflow_coder() -> None:
    await _run(DistillRequest(url="https://example.org/a"), verify_once_failing)
    cfg = settings.distill_workflow
    assert {job.provider for job in jobs} == {cfg.provider}
    assert {job.model for job in jobs} == {cfg.model}
    assert {job.timeout_sec for job in jobs} == {cfg.job_timeout_sec}
    assert len({job.workdir for job in jobs}) == 1


async def test_a_topic_adds_the_file_job_and_its_path_is_the_result() -> None:
    result = await _run(
        DistillRequest(url="https://example.org/a", topic="agents"), verify_once_failing
    )
    assert result.path == FILED["path"]
    assert len(jobs) == 11 and "agents" in jobs[-1].prompt


async def test_an_entry_that_never_passes_verification_fails_the_workflow() -> None:
    with pytest.raises(WorkflowFailureError) as err:
        await _run(DistillRequest(url="https://example.org/a"), verify_always_failing)
    cause = err.value.cause
    assert isinstance(cause, ApplicationError) and cause.type == "EntryNotVerified"
    assert "missing digest.md" in cause.message
    assert len(verified) == settings.distill_workflow.index_attempts


async def test_every_activity_is_labeled_with_its_job_in_the_ui() -> None:
    await _run(DistillRequest(url="https://example.org/a"), verify_once_failing)
    by_kind: dict[str, list[str]] = {}
    for kind, summary in labels:
        by_kind.setdefault(kind, []).append(summary)
    assert by_kind["fetch_source"] == ["https://example.org/a"]
    assert by_kind["verify_entry"] == ["AThing", "AThing"]
    assert sorted(by_kind["extract_structured_output"]) == ["plan"]
    assert sorted(by_kind["execute_job"]) == sorted(
        [
            "plan",
            "wiki/1",
            "wiki/2",
            "digest",
            "summary",
            "explainer",
            "questions",
            "critical thinking",
            "index/1",
            "index/2",
        ]
    )
    jobs_labels = sorted(by_kind["execute_job"])
    assert sorted(by_kind["create_session"]) == sorted(by_kind["build_report"]) == jobs_labels
    assert {job.name for job in jobs} == set(by_kind["execute_job"])
