"""The `research` command: submit and detach, and the request built
from its options."""

from typing import Any

from research.contract import ResearchRequest
from research.settings.load import settings as research_settings
from typer.testing import CliRunner

from temporal_agentic_factory.cli import research as cli
from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.workflows.job import search_attributes


class FakeHandle:
    """Stands in for a workflow handle: only its id is read."""

    def __init__(self, id: str) -> None:
        self.id = id


class FakeClient:
    """Records the start call; stands in for the Temporal client."""

    def __init__(self) -> None:
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}

    async def start_workflow(self, *args: Any, **kwargs: Any) -> FakeHandle:
        self.args = args
        self.kwargs = kwargs
        return FakeHandle(str(kwargs.get("id")))


def _client(monkeypatch: Any) -> FakeClient:
    """The cli's `connect` returning the fake, recording the start."""
    fake = FakeClient()

    async def fake_connect() -> FakeClient:
        return fake

    monkeypatch.setattr(cli, "connect", fake_connect)
    return fake


def _request(client: FakeClient) -> ResearchRequest:
    assert isinstance(client.args[1], ResearchRequest)
    return client.args[1]


def test_detach_prints_the_workflow_id(monkeypatch: Any) -> None:
    client = _client(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "run",
            "research",
            "agents",
            "--focus",
            "What can agents do?",
            "--target",
            "t1",
            "--topic",
            "agents",
            "--detach",
        ],
    )

    assert result.exit_code == 0
    assert client.kwargs["id"].startswith("research-agents-t1-")
    assert client.kwargs["id"] in result.output
    shown = client.kwargs["search_attributes"]
    assert shown.get(search_attributes.NAME) == "agents/t1"


def test_the_request_splits_comma_lists_and_keeps_defaults(monkeypatch: Any) -> None:
    client = _client(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "run",
            "research",
            "agents,safety",
            "--focus",
            "What can agents do?",
            "--target",
            "t1",
            "--topic",
            "agents",
            "--lenses",
            "tech,ai",
            "--kinds",
            "paper,video",
            "--date-from",
            "2025-01",
            "--detach",
        ],
    )

    assert result.exit_code == 0
    request = _request(client)
    assert request.topics == ["agents", "safety"]
    assert request.lenses == ["tech", "ai"]
    assert request.kinds == ["paper", "video"]
    assert request.date_from == "2025-01"
    assert request.n_sources == research_settings.research.n_sources


def test_n_sources_and_workflow_id_pass_through(monkeypatch: Any) -> None:
    client = _client(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "run",
            "research",
            "agents",
            "--focus",
            "What can agents do?",
            "--target",
            "t1",
            "--topic",
            "agents",
            "--n-sources",
            "4",
            "--workflow-id",
            "research-fixed",
            "--detach",
        ],
    )

    assert result.exit_code == 0
    assert _request(client).n_sources == 4
    assert client.kwargs["id"] == "research-fixed"
