"""The `distill` command: the request built from its options, the root among them."""

from pathlib import Path
from typing import Any

from factory_settings import vault
from typer.testing import CliRunner

from distill.contract import DistillRequest
from temporal_agentic_factory.cli import distill as cli
from temporal_agentic_factory.cli.app import app


class FakeHandle:
    """Stands in for a workflow handle: only its id is read."""

    def __init__(self, id: str) -> None:
        self.id = id


class FakeClient:
    """Records the start call; stands in for the Temporal client."""

    def __init__(self) -> None:
        self.args: tuple[Any, ...] = ()

    async def start_workflow(self, *args: Any, **kwargs: Any) -> FakeHandle:
        self.args = args
        return FakeHandle(str(kwargs.get("id")))


def _client(monkeypatch: Any) -> FakeClient:
    """The cli's `connect` returning the fake, recording the start."""
    fake = FakeClient()

    async def fake_connect() -> FakeClient:
        return fake

    monkeypatch.setattr(cli, "connect", fake_connect)
    return fake


def _request(client: FakeClient) -> DistillRequest:
    assert isinstance(client.args[1], DistillRequest)
    return client.args[1]


def test_the_root_defaults_to_the_setting_and_root_reaches_the_request(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _client(monkeypatch)
    base = ["run", "distill", "https://example.com/a", "--topic", "agents"]

    assert CliRunner().invoke(app, [*base, "--detach"]).exit_code == 0
    assert _request(client).root == str(vault.research_topics_dir())

    result = CliRunner().invoke(app, [*base, "--root", str(tmp_path), "--detach"])

    assert result.exit_code == 0
    assert _request(client).root == str(tmp_path.resolve())
