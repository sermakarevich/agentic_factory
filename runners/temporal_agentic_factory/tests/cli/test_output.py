"""`af output` on a temporary sqlite store: the exit codes, `--file`, both
parts saved, a resubmit that replaces, `schema` and `show`. Session s1 is
asked for a report and an output, session s2 for a report only."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from factory_store.store import Store
from typer.testing import CliRunner

from agentic_factory.job.submission.schema import submission_schema
from temporal_agentic_factory.cli import output
from temporal_agentic_factory.cli.app import app

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
    "required": ["urls"],
}
REPORT: dict[str, Any] = {
    "task": "fetch the urls",
    "done": ["urls listed in the output"],
    "not_done": [],
    "problems": [],
    "verdict": "done",
}
runner = CliRunner()


async def _seed(url: str) -> None:
    store = Store.from_url(url)
    await store.create_all()
    await store.start_session("s1", "claude", "m", "/w", "fetch")
    await store.save_output_schema("s1", submission_schema(OUTPUT_SCHEMA))
    await store.start_session("s2", "claude", "m", "/w", "fix")
    await store.save_output_schema("s2", submission_schema(None))
    await store.dispose()


@pytest.fixture(autouse=True)
def store_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A store with sessions s1 and s2 and their schemas; every command opens this one."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'store.db'}"
    asyncio.run(_seed(url))
    monkeypatch.setattr(output, "opened_store", lambda: Store.from_url(url))
    return url


def _submission(urls: list[Any] | None = None, **report: Any) -> str:
    """A submission with the done report, changed by `report`, and the urls when given."""
    submission: dict[str, Any] = {"report": {**REPORT, **report}}
    if urls is not None:
        submission["output"] = {"urls": urls}
    return json.dumps(submission)


def _submit(text: str, session_id: str = "s1") -> tuple[int, str]:
    result = runner.invoke(app, ["output", "submit", session_id], input=text)
    return result.exit_code, result.output


def _show(session_id: str = "s1") -> str:
    return runner.invoke(app, ["output", "show", session_id]).output


def test_a_valid_submission_prints_ok_and_both_parts_are_saved() -> None:
    assert _submit(_submission(["u"])) == (0, "ok\n")

    shown = _show()
    assert shown.startswith("report:\n") and '"fetch the urls"' in shown
    assert "output (source: submitted):\n" in shown and '"u"' in shown


def test_a_report_only_submission_saves_the_report_and_no_output() -> None:
    assert _submit(_submission(), "s2") == (0, "ok\n")

    shown = _show("s2")
    assert shown.startswith("report:\n") and '"verdict": "done"' in shown
    assert shown.endswith("no structured output saved for session s2\n")


def test_an_invalid_submission_lists_its_errors_and_saves_nothing() -> None:
    code, text = _submit(_submission([1], verdict="unknown"))
    assert code == 1
    assert text == (
        "invalid:\n"
        "output.urls[0]: 1 is not of type 'string'\n"
        "report.verdict: 'unknown' is not one of ['done', 'partial', 'failed']\n"
    )
    assert _show() == (
        "no report saved for session s1\nno structured output saved for session s1\n"
    )


def test_a_missing_part_is_an_error_line() -> None:
    assert _submit('{"output": {"urls": []}}') == (
        1,
        "invalid:\n(top): 'report' is a required property\n",
    )
    assert _submit(_submission()) == (1, "invalid:\n(top): 'output' is a required property\n")


def test_bad_json_is_one_line_with_its_place() -> None:
    code, text = _submit('{"report": [')
    assert code == 1 and text.startswith("invalid:\nnot JSON: ") and "line 1 column" in text


def test_an_unknown_session_exits_2() -> None:
    result = runner.invoke(app, ["output", "submit", "nope"], input=_submission())
    assert result.exit_code == 2
    assert runner.invoke(app, ["output", "schema", "nope"]).exit_code == 2


def test_the_json_can_come_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text(_submission(["from-file"]))
    result = runner.invoke(app, ["output", "submit", "s1", "--file", str(path)])
    assert (result.exit_code, result.output) == (0, "ok\n")
    assert "from-file" in _show()


def test_a_later_valid_submission_replaces_the_earlier_one() -> None:
    assert _submit(_submission(["first"], verdict="partial"))[0] == 0
    assert _submit(_submission([2]))[0] == 1
    assert _submit(_submission(["second"]))[0] == 0

    shown = _show()
    assert "second" in shown and "first" not in shown
    assert '"done"' in shown and '"partial"' not in shown


def test_schema_prints_the_whole_submission_schema() -> None:
    result = runner.invoke(app, ["output", "schema", "s1"])
    assert result.exit_code == 0 and json.loads(result.output) == submission_schema(OUTPUT_SCHEMA)
    assert json.loads(runner.invoke(app, ["output", "schema", "s2"]).output)["required"] == [
        "report"
    ]
