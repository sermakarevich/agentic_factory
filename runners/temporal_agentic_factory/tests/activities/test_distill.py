from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from distill.contract import DistillRequest, EntryType, FetchedSource
from distill.sources import SourceError
from temporal_agentic_factory.activities import distill as activity

REQUEST = activity.FetchRequest(
    request=DistillRequest(url="https://example.org/a"), work_dir="/tmp/run-1"
)
FETCHED = FetchedSource(
    work_dir="/tmp/run-1",
    source_md="/tmp/run-1/source.md",
    title="A",
    kind="article",
    type=EntryType.article,
    fetched_at="2026-09-30T00:00:00+00:00",
    chunks=[],
)


async def test_the_app_fetches_the_request_under_the_work_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    given: list[tuple[DistillRequest, Path]] = []

    def fake_fetch(request: DistillRequest, work_dir: Path) -> FetchedSource:
        given.append((request, work_dir))
        return FETCHED

    monkeypatch.setattr(activity.fetch, "fetch_source", fake_fetch)
    found = await ActivityEnvironment().run(activity.fetch_source, REQUEST)
    assert found == FETCHED
    assert given == [(REQUEST.request, Path("/tmp/run-1"))]


@pytest.mark.parametrize(
    ("error", "kind", "final"),
    [
        (SourceError("yt: rate limited", transient=True), "SourceError", False),
        (SourceError("no such file"), "SourceError", True),
        (ValueError("unknown topic: x"), "BadTopic", True),
    ],
)
async def test_only_a_transient_source_error_is_retried(
    monkeypatch: pytest.MonkeyPatch, error: Exception, kind: str, final: bool
) -> None:
    def fake_fetch(request: DistillRequest, work_dir: Path) -> FetchedSource:
        raise error

    monkeypatch.setattr(activity.fetch, "fetch_source", fake_fetch)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(activity.fetch_source, REQUEST)
    assert err.value.type == kind and err.value.non_retryable is final
    assert str(error) in err.value.message


async def test_verify_reports_the_entry_folder_problems(tmp_path: Path) -> None:
    problems = await ActivityEnvironment().run(activity.verify_entry, str(tmp_path))
    assert "verify: missing index.md" in problems
    assert "verify: wiki/ holds no pages" in problems
