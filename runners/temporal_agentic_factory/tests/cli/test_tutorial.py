"""The `tutorial` command: its help, submit and detach, and the request
built from its options."""

from typing import Any

from tutorial.contract import Format, TutorialRequest, tutorials_dir
from tutorial.settings.load import settings as tutorial_settings
from typer.testing import CliRunner

from temporal_agentic_factory.cli import tutorial as cli
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
    monkeypatch.setattr(cli, "refuse_unconfigured", lambda *providers: None)
    return fake


def _request(client: FakeClient) -> TutorialRequest:
    assert isinstance(client.args[1], TutorialRequest)
    return client.args[1]


def test_help_names_every_option() -> None:
    result = CliRunner().invoke(app, ["run", "tutorial", "--help"])

    assert result.exit_code == 0
    for option in ("--name", "--formats", "--level", "--review-rounds", "--detach"):
        assert option in result.output


def test_detach_prints_the_workflow_id(monkeypatch: Any) -> None:
    client = _client(monkeypatch)

    result = CliRunner().invoke(app, ["run", "tutorial", "Grafana dashboards", "--detach"])

    assert result.exit_code == 0
    assert client.kwargs["id"].startswith("tutorial-grafana-dashboards-")
    assert client.kwargs["id"] in result.output
    assert client.kwargs["static_summary"] == "Grafana dashboards"
    shown = client.kwargs["search_attributes"]
    assert shown.get(search_attributes.NAME) == "Grafana dashboards"


def test_options_left_out_keep_the_settings_defaults(monkeypatch: Any) -> None:
    client = _client(monkeypatch)

    result = CliRunner().invoke(app, ["run", "tutorial", "Grafana dashboards", "--detach"])

    assert result.exit_code == 0
    request = _request(client)
    assert request.name == ""
    assert request.root == str(tutorials_dir())
    assert request.formats == [Format(item) for item in tutorial_settings.tutorial.formats]
    assert request.level == tutorial_settings.tutorial.level
    assert request.review_rounds == tutorial_settings.tutorial.review_rounds
    assert request.writer.provider == tutorial_settings.writer.provider
    assert request.writer.model == tutorial_settings.writer.model


def test_the_options_pass_through(monkeypatch: Any) -> None:
    client = _client(monkeypatch)

    result = CliRunner().invoke(
        app,
        [
            "run",
            "tutorial",
            "Grafana dashboards",
            "--name",
            "grafana",
            "--root",
            "/kb/elsewhere",
            "--formats",
            "ipynb",
            "--level",
            "advanced",
            "--review-rounds",
            "1",
            "--writer-provider",
            "claude",
            "--reviewer-model",
            "opus",
            "--workflow-id",
            "tutorial-fixed",
            "--detach",
        ],
    )

    assert result.exit_code == 0
    request = _request(client)
    assert (request.name, request.formats, request.level) == ("grafana", [Format.ipynb], "advanced")
    assert request.review_rounds == 1
    assert request.root == "/kb/elsewhere"
    assert (request.writer.provider, request.writer.model) == ("claude", "")
    assert request.reviewer.provider == tutorial_settings.reviewer.provider
    assert request.reviewer.model == "opus"
    assert client.kwargs["id"] == "tutorial-fixed"
    assert client.kwargs["search_attributes"].get(search_attributes.NAME) == "grafana"


def test_a_bad_level_is_refused(monkeypatch: Any) -> None:
    client = _client(monkeypatch)

    result = CliRunner().invoke(
        app, ["run", "tutorial", "Grafana", "--level", "expert", "--detach"]
    )

    assert result.exit_code != 0
    assert client.args == ()
