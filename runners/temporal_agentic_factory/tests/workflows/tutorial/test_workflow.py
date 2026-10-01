"""The tutorial workflow, run to a result: the designer's plan, three
chapters written at once (one passes, one passes after a rewrite, one keeps
failing and ends failed), then the finish job. Every job is faked; nothing
is written anywhere."""

import uuid
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from tutorial.contract import (
    Chapter,
    ChapterStatus,
    Format,
    TutorialOutcome,
    TutorialPlan,
    TutorialRequest,
)

from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.tokens import Tokens
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.execute import TryResult
from temporal_agentic_factory.workflows.job.report import ReportRequest
from temporal_agentic_factory.workflows.job.workflow import JobWorkflow
from temporal_agentic_factory.workflows.structured_output.extract import StructuredOutputRequest
from temporal_agentic_factory.workflows.structured_output.workflow import (
    JobWithStructuredOutputWorkflow,
)
from temporal_agentic_factory.workflows.tutorial.workflow import TutorialWorkflow
from tests.workers import running

INDEX_PATH = "/tmp/tutorials/grafana/index.md"
STUCK = "the notebook does not run"


def _chapter(number: int, slug: str) -> Chapter:
    return Chapter(
        number=number,
        slug=slug,
        title=slug.title(),
        spec_path=f"specs/{number:02d}_{slug}.md",
        formats=[Format.md],
        outputs=[f"{number:02d}_{slug}.md"],
    )


PLAN = TutorialPlan(
    title="Grafana",
    project=True,
    chapters=[_chapter(1, "setup"), _chapter(2, "panels"), _chapter(3, "alerts")],
)

jobs: list[Job] = []
located: list[str] = []
designed = {"plan": PLAN}  # what the fake designer states; a test may swap it


@activity.defn(name="locate_tutorial")
async def fake_locate(folder: str) -> str:
    located.append(folder)
    return folder


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    """The session is named by its job, so the extraction knows whose it reads."""
    return f"session:{job.name}"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> TryResult:
    jobs.append(job)
    result = JobResult(
        session_id=job.session_id,
        cost_usd=0.1,
        tokens=Tokens(input=10, output=5),
        usage_known=True,
    )
    return TryResult(result=result, runner="r1")


@activity.defn(name="build_report")
async def fake_report(request: ReportRequest) -> JobReport:
    return JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.DONE)


@activity.defn(name="record_job")
async def fake_record(outcome: JobOutcome) -> None:
    return None


@activity.defn(name="extract_structured_output")
async def fake_extract(request: StructuredOutputRequest) -> dict[str, Any]:
    """The name, the plan, a review or the index, by the job whose session it is.
    Chapter 01 passes, 02 passes once rewritten, 03 never passes."""
    name = request.session_id.removeprefix("session:")
    if name == "name":
        return {"name": "picked"}
    if name == "design":
        stated: dict[str, Any] = designed["plan"].model_dump(mode="json")
        return stated
    if name == "finish":
        return {"index_path": INDEX_PATH, "fixes": ["one link fixed"]}
    if name in ("review/01", "review/02/1"):
        return {"passed": True, "problems": []}
    if name.startswith("review/"):
        return {"passed": False, "problems": [STUCK]}
    raise AssertionError(f"no fake output for {name}")


async def _run(request: TutorialRequest) -> TutorialOutcome:
    jobs.clear()
    located.clear()
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    async with env:
        await search_attributes.add(
            env.client, "default", [key.name for key in search_attributes.KEYS]
        )
        queue = f"test-{uuid.uuid4()}"
        async with running(
            env.client,
            queue,
            [TutorialWorkflow, JobWorkflow, JobWithStructuredOutputWorkflow],
            [fake_locate, fake_session, fake_report, fake_record, fake_extract],
            fake_job,
        ):
            return await env.client.execute_workflow(
                TutorialWorkflow.run,
                request,
                id=f"tutorial-grafana-{uuid.uuid4().hex[:4]}",
                task_queue=queue,
            )


def _request(name: str = "grafana") -> TutorialRequest:
    return TutorialRequest(topic="Grafana dashboards", name=name, review_rounds=2)


async def test_a_chapter_that_keeps_failing_ends_failed_and_the_others_finish() -> None:
    result = await _run(_request())

    assert result.title == "Grafana" and result.index_path == INDEX_PATH
    assert result.folder.endswith("/grafana") and located == [result.folder]
    statuses = [(item.slug, item.status, item.rewrites) for item in result.chapters]
    assert statuses == [
        ("setup", ChapterStatus.done, 0),
        ("panels", ChapterStatus.done, 1),
        ("alerts", ChapterStatus.failed, 2),
    ]
    assert result.chapters[2].problems == [STUCK]
    assert result.chapters[1].problems == [] and result.fixes == ["one link fixed"]


async def test_every_job_runs_in_the_story_order() -> None:
    await _run(_request())

    names = [job.name for job in jobs]
    assert names[0] == "design" and names[-1] == "finish"
    assert sorted(names[1:-1]) == sorted(
        [
            "write/01",
            "review/01",
            "write/02",
            "review/02",
            "rewrite/02/1",
            "review/02/1",
            "write/03",
            "review/03",
            "rewrite/03/1",
            "review/03/1",
            "rewrite/03/2",
            "review/03/2",
        ]
    )
    rewrite = next(job for job in jobs if job.name == "rewrite/03/2")
    assert STUCK in rewrite.prompt


async def test_the_spend_is_summed_per_chapter_and_in_total() -> None:
    result = await _run(_request())

    assert [item.spend.jobs for item in result.chapters] == [2, 4, 6]
    assert result.spend.jobs == 14 and result.spend.unknown == 0
    assert result.spend.cost_usd == pytest.approx(1.4)
    assert (result.spend.input_tokens, result.spend.output_tokens) == (140, 70)


async def test_no_name_runs_the_naming_job_first() -> None:
    result = await _run(_request(name=""))

    assert jobs[0].name == "name" and jobs[1].name == "design"
    assert result.folder.endswith("/picked") and located == [result.folder]


async def test_a_plan_that_cannot_be_built_stops_before_any_writer(monkeypatch: Any) -> None:
    twice = PLAN.model_copy(update={"chapters": [_chapter(1, "setup"), _chapter(1, "setup")]})
    monkeypatch.setitem(designed, "plan", twice)

    with pytest.raises(WorkflowFailureError) as raised:
        await _run(_request())

    cause = raised.value.cause
    assert isinstance(cause, ApplicationError) and cause.type == "BadPlan"
    assert [job.name for job in jobs] == ["design"]
