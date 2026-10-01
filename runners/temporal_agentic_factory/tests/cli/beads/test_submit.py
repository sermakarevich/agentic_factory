"""`af beads add/set/retry` over a fake `bd` in a temp home."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.beads import opened
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.markers import RETRY
from tests.fake_bd import FakeBd

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


def _bd(monkeypatch: Any, home: Path, bd: FakeBd) -> FakeBd:
    """The cli's database at `home`, answered by `bd`."""
    monkeypatch.setattr(settings.beads, "home", str(home))
    monkeypatch.setattr(opened, "run_bd", bd)
    return bd


def _initialised(tmp_path: Path) -> Path:
    (tmp_path / ".beads").mkdir(parents=True)
    return tmp_path


def _invoke(*args: str) -> Any:
    return CliRunner().invoke(app, ["beads", *args])


def _metadata(args: list[str]) -> Any:
    return json.loads(args[args.index("--metadata") + 1])


def _shown(status: str, job_fields: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [{"id": "af-1", "status": status, "metadata": {"af_job": job_fields or {}}}]


def test_add_writes_only_the_options_given_and_prints_the_id(
    monkeypatch: Any, tmp_path: Path
) -> None:
    home = _initialised(tmp_path / "home")
    repo = tmp_path / "repo"
    repo.mkdir()
    bd = _bd(monkeypatch, home, FakeBd({"create": "af-7\n"}))
    result = _invoke("add", "Fix it", "--cwd", str(repo), "--provider", "opencode", "--body", "B")
    assert result.exit_code == 0, result.output
    assert result.stdout == "af-7\n"
    args, cwd, _ = bd.calls[0]
    assert cwd == home
    assert args[args.index("--description") + 1] == "B"
    assert args[args.index("--priority") + 1] == str(settings.beads.default_priority)
    assert _metadata(args) == {"af_job": {"provider": "opencode", "workdir": str(repo.resolve())}}


def test_add_maps_every_job_option(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path / "h"), FakeBd({"create": "af-8"}))
    result = _invoke(
        "add", "T", "--workdir", str(tmp_path), "--provider", "claude", "--model", "opus",
        "--name", "n", "--tools", "Read,Edit", "--timeout-sec", "60", "--stall-sec", "30",
        "--context-limit-tokens", "1000", "--structured-output", json.dumps(SCHEMA),
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert _metadata(bd.calls[0][0])["af_job"] == {
        "provider": "claude",
        "model": "opus",
        "name": "n",
        "workdir": str(tmp_path.resolve()),
        "tools": ["Read", "Edit"],
        "timeout_sec": 60,
        "stall_sec": 30,
        "context_limit_tokens": 1000,
        "structured_output": SCHEMA,
    }


def test_add_without_job_options_writes_an_empty_af_job(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"create": "af-8"}))
    result = _invoke("add", "T", "--body", "---\nworkdir: /tmp\n---\nfront matter routes it")
    assert result.exit_code == 0, result.output
    assert _metadata(bd.calls[0][0]) == {"af_job": {}}


def test_add_reads_a_structured_output_file(monkeypatch: Any, tmp_path: Path) -> None:
    schema_file = tmp_path / "s.json"
    schema_file.write_text(json.dumps(SCHEMA))
    bd = _bd(monkeypatch, _initialised(tmp_path / "h"), FakeBd({"create": "af-8"}))
    result = _invoke("add", "T", "--structured-output", f"@{schema_file}")
    assert result.exit_code == 0, result.output
    assert _metadata(bd.calls[0][0])["af_job"] == {"structured_output": SCHEMA}


def test_add_refuses_an_unreadable_schema(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd())
    result = _invoke("add", "T", "--structured-output", "{not json")
    assert result.exit_code == 1
    assert "--structured-output" in result.output
    assert bd.calls == []


def test_add_places_the_bead_in_a_chain(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"create": "af-9"}))
    result = _invoke(
        "add", "T", "--after", "af-1", "--after", "af-2", "--parent", "af-0",
        "--label", "x", "--label", "y", "--type", "bug", "--id", "af-9",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert result.stdout == "af-9\n"
    assert len(bd.calls) == 1
    args = bd.calls[0][0]
    assert args[args.index("--deps") + 1] == "af-1,af-2"
    assert args[args.index("--parent") + 1] == "af-0"
    assert args[args.index("--labels") + 1] == "x,y"
    assert args[args.index("--type") + 1] == "bug"
    assert args[args.index("--id") + 1] == "af-9"


def test_add_takes_priority_and_a_body_file(monkeypatch: Any, tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("from a file")
    bd = _bd(monkeypatch, _initialised(tmp_path / "h"), FakeBd({"create": "af-8"}))
    result = _invoke("add", "T", "--priority", "0", "--body-file", str(body))
    assert result.exit_code == 0, result.output
    args = bd.calls[0][0]
    assert args[args.index("--description") + 1] == "from a file"
    assert args[args.index("--priority") + 1] == "0"


def test_add_refuses_an_unconfigured_provider(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd())
    result = _invoke("add", "T", "--cwd", str(tmp_path), "--provider", "codex")
    assert result.exit_code == 1
    assert "[providers.codex]" in result.output
    assert bd.calls == []


def test_add_refuses_a_workdir_that_is_not_a_directory(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd())
    result = _invoke("add", "T", "--workdir", str(tmp_path / "nope"))
    assert result.exit_code != 0
    assert bd.calls == []


def test_add_refuses_body_and_body_file_together(monkeypatch: Any, tmp_path: Path) -> None:
    body = tmp_path / "b.md"
    body.write_text("x")
    _bd(monkeypatch, _initialised(tmp_path / "h"), FakeBd())
    result = _invoke("add", "T", "--body", "y", "--body-file", str(body))
    assert result.exit_code == 1
    assert "not both" in result.output


def test_add_refuses_a_priority_out_of_range(monkeypatch: Any, tmp_path: Path) -> None:
    _bd(monkeypatch, _initialised(tmp_path), FakeBd())
    assert _invoke("add", "T", "--priority", "5").exit_code != 0


def test_set_merges_into_af_job(monkeypatch: Any, tmp_path: Path) -> None:
    current = {"provider": "opencode", "workdir": "/tmp", "model": "old"}
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"show": _shown("open", current)}))
    result = _invoke("set", "af-1", "--model", "new", "--timeout-sec", "60")
    assert result.exit_code == 0, result.output
    update = bd.calls[-1][0]
    assert update[:2] == ["update", "af-1"]
    assert _metadata(update) == {"af_job": current | {"model": "new", "timeout_sec": 60}}


def test_set_works_on_a_blocked_bead(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"show": _shown("blocked")}))
    assert _invoke("set", "af-1", "--model", "m").exit_code == 0
    assert bd.calls[-1][0][0] == "update"


@pytest.mark.parametrize("status", ["in_progress", "closed"])
def test_set_refuses_a_bead_whose_job_runs_or_ran(
    monkeypatch: Any, tmp_path: Path, status: str
) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"show": _shown(status)}))
    result = _invoke("set", "af-1", "--model", "m")
    assert result.exit_code == 1
    assert status in result.output
    assert [args[0] for args, _, _ in bd.calls] == ["show"]


def test_set_refuses_no_options(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"show": _shown("open")}))
    result = _invoke("set", "af-1")
    assert result.exit_code == 1
    assert bd.calls == []


def test_retry_comments_then_reopens_a_blocked_bead(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"show": _shown("blocked")}))
    result = _invoke("retry", "af-1", "--reason", "flaky network")
    assert result.exit_code == 0, result.output
    assert result.stdout == "af-1\n"
    assert [args for args, _, _ in bd.calls][1:] == [
        ["comment", "af-1", f"{RETRY}: flaky network"],
        ["update", "af-1", "--status", "open"],
    ]


def test_retry_refuses_a_bead_that_is_not_blocked(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({"show": _shown("open")}))
    result = _invoke("retry", "af-1")
    assert result.exit_code == 1
    assert "not blocked" in result.output
    assert len(bd.calls) == 1


def test_retry_leaves_the_bead_blocked_when_its_comment_fails(
    monkeypatch: Any, tmp_path: Path
) -> None:
    bd = _bd(
        monkeypatch,
        _initialised(tmp_path),
        FakeBd({"show": _shown("blocked")}, failing={"comment"}),
    )
    result = _invoke("retry", "af-1")
    assert result.exit_code == 1
    assert "update" not in [args[0] for args, _, _ in bd.calls]


@pytest.mark.parametrize(
    "command", [["add", "T"], ["set", "af-1", "--model", "m"], ["retry", "af-1"]]
)
def test_submit_commands_refuse_a_missing_database(
    monkeypatch: Any, tmp_path: Path, command: list[str]
) -> None:
    bd = _bd(monkeypatch, tmp_path / "none", FakeBd())
    result = _invoke(*command)
    assert result.exit_code == 1
    assert "af beads init" in result.output
    assert bd.calls == []
