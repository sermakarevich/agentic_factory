"""`af output` on a temporary sqlite store: the exit codes, `--file`, a
resubmit that replaces, `schema` and `show`."""

import asyncio
import json
from pathlib import Path

import pytest
from factory_store.store import Store
from typer.testing import CliRunner

from temporal_agentic_factory.cli import output
from temporal_agentic_factory.cli.app import app

SCHEMA = {
    "type": "object",
    "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
    "required": ["urls"],
}
runner = CliRunner()


async def _seed(url: str) -> None:
    store = Store.from_url(url)
    await store.create_all()
    await store.start_session("s1", "claude", "m", "/w", "fetch")
    await store.save_output_schema("s1", SCHEMA)
    await store.dispose()


@pytest.fixture(autouse=True)
def store_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A store with session s1 and its schema; every command opens this one."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'store.db'}"
    asyncio.run(_seed(url))
    monkeypatch.setattr(output, "opened_store", lambda: Store.from_url(url))
    return url


def _submit(text: str, session_id: str = "s1") -> tuple[int, str]:
    result = runner.invoke(app, ["output", "submit", session_id], input=text)
    return result.exit_code, result.output


def test_a_valid_submission_prints_ok_and_is_saved() -> None:
    assert _submit('{"urls": ["u"]}') == (0, "ok\n")

    shown = runner.invoke(app, ["output", "show", "s1"])
    assert shown.exit_code == 0
    assert shown.output.startswith("source: submitted\n") and '"u"' in shown.output


def test_an_invalid_submission_lists_its_errors_and_saves_nothing() -> None:
    code, text = _submit('{"urls": [1]}')
    assert code == 1
    assert text == "invalid:\nurls[0]: 1 is not of type 'string'\n"

    shown = runner.invoke(app, ["output", "show", "s1"])
    assert shown.output == "no structured output saved for session s1\n"


def test_bad_json_is_one_line_with_its_place() -> None:
    code, text = _submit('{"urls": [')
    assert code == 1 and text.startswith("invalid:\nnot JSON: ") and "line 1 column" in text


def test_an_unknown_session_exits_2() -> None:
    result = runner.invoke(app, ["output", "submit", "nope"], input='{"urls": []}')
    assert result.exit_code == 2
    assert runner.invoke(app, ["output", "schema", "nope"]).exit_code == 2


def test_the_json_can_come_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text('{"urls": ["from-file"]}')
    result = runner.invoke(app, ["output", "submit", "s1", "--file", str(path)])
    assert (result.exit_code, result.output) == (0, "ok\n")
    assert "from-file" in runner.invoke(app, ["output", "show", "s1"]).output


def test_a_later_valid_submission_replaces_the_earlier_one() -> None:
    assert _submit('{"urls": ["first"]}')[0] == 0
    assert _submit('{"urls": [2]}')[0] == 1
    assert _submit('{"urls": ["second"]}')[0] == 0

    shown = runner.invoke(app, ["output", "show", "s1"]).output
    assert "second" in shown and "first" not in shown


def test_schema_prints_the_saved_schema() -> None:
    result = runner.invoke(app, ["output", "schema", "s1"])
    assert result.exit_code == 0 and json.loads(result.output) == SCHEMA
