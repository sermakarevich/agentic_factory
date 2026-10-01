"""The research workflow, run to a result: one focus question through
discovery, ranking, the plan, two child distill runs (one filed, one
dead), the digests, the aggregates, one lens and the index."""

import uuid
from typing import Any

from research.contract import (
    Candidate,
    Discovered,
    Lens,
    PlannedSource,
    ResearchPlan,
    ResearchRequest,
    Status,
    Subtopic,
)
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.step.judge.answer import ChoiceAnswer, ScoreAnswer
from agentic_factory.step.judge.contract import Judgment, JudgmentResult
from distill.contract import DistillRequest, EntryPlan, EntryType, FetchedSource
from temporal_agentic_factory.distill.workflow import DistilledEntry
from temporal_agentic_factory.job import search_attributes
from temporal_agentic_factory.job.execute import TryResult
from temporal_agentic_factory.job.report import ReportRequest
from temporal_agentic_factory.research.workflow import ResearchWorkflow
from temporal_agentic_factory.structured_output.extract import StructuredOutputRequest

TARGET_DIR = "/tmp/research/t1"
INDEX_PATH = "/tmp/research/t1/index.md"
DEAD_REASON = "source unreachable: 404"
FILED_PATH = "/kb/research_topics/agents/Alpha"


def _candidate(title: str, kind: str, date: str, status: Status, origin: str = "") -> Candidate:
    return Candidate(
        url=f"https://example.com/{title.lower()}",
        title=title,
        kind=kind,
        authors="Ada",
        date=date,
        venue="arXiv",
        abstract=f"About {title}.",
        status=status,
        origin=origin,
    )


CANDIDATES = Discovered(
    candidates=[
        _candidate("Alpha", "paper", "2026-01-01", Status.candidate),
        _candidate("Beta", "article", "2026-02-01", Status.candidate),
        _candidate("Old", "article", "2025-06-01", Status.in_kb, "research/Old"),
    ]
)

PLAN = ResearchPlan(
    sources=[
        PlannedSource(
            key="src-01",
            url="https://example.com/alpha",
            title="Alpha",
            kind="paper",
            subtopic="agents",
        ),
        PlannedSource(
            key="src-02",
            url="https://example.com/dead",
            title="Dead",
            kind="video",
            subtopic="agents",
        ),
    ],
    subtopics=[
        Subtopic(
            nn="01",
            subtopic="agents",
            title="Agents",
            sources=["src-01", "src-02"],
            linked=[],
        )
    ],
    lenses=[Lens(lens="tech", audience="engineers")],
)

jobs: list[Job] = []


@activity.defn(name="locate_target")
async def fake_locate(request: ResearchRequest) -> str:
    return TARGET_DIR


@activity.defn(name="read_candidates")
async def fake_candidates(path: str) -> Discovered:
    return CANDIDATES


@activity.defn(name="judge")
async def fake_judge(judgment: Judgment) -> JudgmentResult:
    """Beta outranks Alpha; the kind and authority answers never differ."""
    state = judgment.state
    title = state.get("title") if isinstance(state, dict) else None
    relevance = 0.9 if title == "Beta" else 0.2
    return JudgmentResult(
        answers={
            "relevance": ScoreAnswer(
                score=relevance,
                confidence=0.9,
                probabilities={0: 0.0, 1: 0.0, 2: 0.1, 3: 0.9},
                legend={0: "irrelevant", 1: "tangential", 2: "relevant", 3: "central"},
            ),
            "kind": ChoiceAnswer(
                choice="survey",
                confidence=0.8,
                probabilities={"survey": 0.8, "tutorial": 0.2},
            ),
            "authority": ChoiceAnswer(
                choice="established-blog",
                confidence=0.7,
                probabilities={"established-blog": 0.7, "unknown": 0.3},
            ),
        },
        model="jev-stub",
    )


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
    """The candidates path, the plan, or the index path, by the schema asked for."""
    props = request.output_schema["properties"]
    if "candidates_path" in props:
        return {"candidates_path": "/tmp/research/t1/candidates.json"}
    if "sources" in props:
        return PLAN.model_dump()
    if "index_path" in props:
        return {"index_path": INDEX_PATH}
    raise AssertionError(f"no fake output for {sorted(props)}")


@workflow.defn(name="distill", sandboxed=False)
class FakeDistillWorkflow:
    """A child distill run: files every source but the dead one. Unsandboxed:
    it lives in the test module, which the sandbox cannot re-import."""

    @workflow.run
    async def run(self, request: DistillRequest) -> DistilledEntry:
        if "dead" in request.url:
            raise ApplicationError(DEAD_REASON, type="SourceError", non_retryable=True)
        return DistilledEntry(
            path=FILED_PATH,
            plan=EntryPlan(
                research_dir=FILED_PATH, slug="Alpha", title="Alpha", type=EntryType.article
            ),
            fetched=FetchedSource(
                work_dir="/tmp/fetch",
                source_md="/tmp/fetch/source.md",
                title="Alpha",
                kind="article",
                type=EntryType.article,
                fetched_at="2026-09-30T00:00:00+00:00",
                chunks=[],
            ),
        )


async def _run(request: ResearchRequest):  # type: ignore[no-untyped-def]
    jobs.clear()
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    async with env:
        await search_attributes.add(
            env.client, "default", [key.name for key in search_attributes.KEYS]
        )
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[ResearchWorkflow, FakeDistillWorkflow],
            activities=[
                fake_locate,
                fake_candidates,
                fake_judge,
                fake_session,
                fake_job,
                fake_report,
                fake_record,
                fake_extract,
            ],
        ):
            handle = await env.client.start_workflow(
                ResearchWorkflow.run,
                request,
                id=f"research-{uuid.uuid4()}",
                task_queue=queue,
            )
            return await handle.result()


def _request() -> ResearchRequest:
    return ResearchRequest(
        topics=["agents"], focus="What can agents do?", target="t1", topic="agents"
    )


async def test_a_dead_source_is_skipped_and_a_filed_one_is_kept() -> None:
    result = await _run(_request())

    assert result.target_dir == TARGET_DIR and result.index_path == INDEX_PATH
    assert result.plan == PLAN
    (first, second) = result.sources
    assert (first.key, first.status, first.path) == ("src-01", "succeeded", FILED_PATH)
    assert (second.key, second.status) == ("src-02", "skipped")
    assert second.reason == DEAD_REASON and second.path == ""


async def test_the_ranking_orders_by_relevance_and_keeps_the_kb_match() -> None:
    result = await _run(_request())

    assert [(item.title, item.status) for item in result.candidates] == [
        ("Beta", "shortlist"),
        ("Alpha", "shortlist"),
        ("Old", "in_kb"),
    ]
    beta, alpha = result.candidates[0].scores, result.candidates[1].scores
    assert beta is not None and alpha is not None and beta.relevance > alpha.relevance
    assert beta.kind == "survey" and beta.authority == "established-blog"


async def test_every_job_runs_in_the_story_order() -> None:
    await _run(_request())

    names = [job.name for job in jobs]
    assert names[:3] == ["discover", "assign", "topic/01"]
    assert sorted(names[3:8]) == [
        "agreements",
        "digest",
        "disagreements",
        "open_questions",
        "overview",
    ]
    assert names[8:] == ["lens/tech", "index"]
