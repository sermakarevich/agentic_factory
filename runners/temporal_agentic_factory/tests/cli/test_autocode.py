"""The `autocode` command: its help, submit and detach, and the request
built from its options."""

from pathlib import Path
from typing import Any

from autocode.contract import AutocodeRequest
from autocode.settings.load import settings as autocode_settings
from typer.testing import CliRunner

from temporal_agentic_factory.cli import autocode as cli
from temporal_agentic_factory.cli.app import app


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


def _request(client: FakeClient) -> AutocodeRequest:
    assert isinstance(client.args[1], AutocodeRequest)
    return client.args[1]


def _invoke(*options: str) -> Any:
    return CliRunner().invoke(app, ["run", "autocode", "--detach", *options])


def test_help_names_every_option() -> None:
    result = CliRunner().invoke(app, ["run", "autocode", "--help"])

    assert result.exit_code == 0
    for option in ("--repo", "--feature", "--spec", "--provider", "--model", "--detach"):
        assert option in result.output
    assert "--workflow-id" in result.output


def test_af_run_lists_autocode() -> None:
    assert "autocode" in CliRunner().invoke(app, ["run", "--help"]).output


def test_detach_prints_the_workflow_id_and_keeps_the_settings_coder(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _client(monkeypatch)

    result = _invoke("--repo", str(tmp_path), "--feature", "csv", "--spec", "Export rows.")

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == client.kwargs["id"]
    assert client.kwargs["id"].startswith("autocode-")
    request = _request(client)
    assert request.repo == str(tmp_path.resolve()) and request.spec == "Export rows."
    assert request.provider == autocode_settings.autocode.provider
    assert request.review_model == autocode_settings.autocode.review_model


def test_a_spec_file_and_a_relative_repo_are_made_absolute(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _client(monkeypatch)
    (tmp_path / "spec.md").write_text("# Export\n")
    monkeypatch.chdir(tmp_path)

    _invoke("--repo", ".", "--feature", "csv", "--spec", "spec.md")

    request = _request(client)
    assert request.repo == str(tmp_path.resolve())
    assert request.spec == str((tmp_path / "spec.md").resolve()) and request.spec_is_file


def test_a_new_provider_alone_runs_every_job_on_its_default_model(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _client(monkeypatch)

    _invoke("--repo", str(tmp_path), "--feature", "csv", "--spec", "s", "--provider", "codex")

    request = _request(client)
    assert (request.provider, request.model, request.review_model) == ("codex", "", "")


def test_a_bad_feature_slug_is_refused(monkeypatch: Any, tmp_path: Path) -> None:
    _client(monkeypatch)

    result = _invoke("--repo", str(tmp_path), "--feature", "Bad Slug", "--spec", "s")

    assert result.exit_code != 0
