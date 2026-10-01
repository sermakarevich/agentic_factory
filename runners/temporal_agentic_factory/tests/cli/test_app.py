import re

import pytest
import typer
import typer.main
from typer._completion_classes import BashComplete
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.errors import (
    normalize_status,
    normalize_workflow_type,
    run_coro,
)
from temporal_agentic_factory.cli.ids import new_id
from temporal_agentic_factory.settings.load import settings

WORKFLOWS = ("job", "research", "distill", "tutorial", "autocode")


def test_cli_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "runner" in result.output and "coders" in result.output


def test_cli_run_lists_every_workflow() -> None:
    for args in (["run"], ["run", "--help"]):
        listing = CliRunner().invoke(app, args).output
        for workflow in WORKFLOWS:
            assert workflow in listing


def test_cli_run_reaches_every_workflow() -> None:
    for workflow in WORKFLOWS:
        result = CliRunner().invoke(app, ["run", workflow, "--help"])
        assert result.exit_code == 0, workflow
        assert "--detach" in result.output and "--workflow-id" in result.output


def test_cli_run_refuses_an_unknown_workflow() -> None:
    result = CliRunner().invoke(app, ["run", "x"])
    assert result.exit_code == 1
    assert "unknown workflow 'x'; choose from: job, research, distill, tutorial" in result.output
    assert "to run a job" not in result.output


def test_cli_run_hints_the_job_form_for_an_old_style_prompt() -> None:
    result = CliRunner().invoke(app, ["run", "some prompt", "--detach"])
    assert result.exit_code == 1
    assert "unknown workflow 'some prompt'; choose from: job, research, distill" in result.output
    assert 'to run a job: af run job "<prompt>"' in result.output


def test_cli_run_completes_the_workflow_names() -> None:
    complete = BashComplete(typer.main.get_command(app), {}, "af", "_AF_COMPLETE")
    assert [item.value for item in complete.get_completions(["run"], "")] == list(WORKFLOWS)
    assert [item.value for item in complete.get_completions(["run"], "t")] == ["tutorial"]


def test_cli_has_no_top_level_workflow_commands() -> None:
    for workflow in ("research", "distill", "tutorial"):
        assert CliRunner().invoke(app, [workflow, "--help"]).exit_code != 0, workflow


def test_cli_offers_distill() -> None:
    result = CliRunner().invoke(app, ["run", "distill", "--help"])
    assert result.exit_code == 0
    assert "--topic" in result.output and "--research-target" in result.output
    assert "--target-dir" in result.output


def test_cli_run_takes_a_job_name() -> None:
    result = CliRunner().invoke(app, ["run", "job", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output


def test_cli_run_offers_detach_and_workflow_id() -> None:
    result = CliRunner().invoke(app, ["run", "job", "--help"])
    assert result.exit_code == 0
    assert "--detach" in result.output
    assert "--workflow-id" in result.output
    assert "--force" not in result.output


def test_cli_distill_offers_detach_and_workflow_id() -> None:
    result = CliRunner().invoke(app, ["run", "distill", "--help"])
    assert result.exit_code == 0
    assert "--detach" in result.output
    assert "--workflow-id" in result.output


def test_cli_offers_workflow_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("status", "result", "list", "cancel", "terminate", "health", "worker"):
        assert command in result.output


def test_cli_status_and_list_help() -> None:
    assert CliRunner().invoke(app, ["status", "--help"]).exit_code == 0
    assert CliRunner().invoke(app, ["list", "--help"]).exit_code == 0
    list_help = CliRunner().invoke(app, ["list", "--help"]).output
    assert "--status" in list_help and "--type" in list_help


def test_cli_beads_group() -> None:
    assert CliRunner().invoke(app, ["beads", "--help"]).exit_code == 0
    group = CliRunner().invoke(app, ["beads", "--help"]).output
    for command in ("init", "add", "list", "show", "close", "ready", "poll", "start", "status"):
        assert command in group


def test_new_id_uses_given_id() -> None:
    assert new_id("job", "fix login", "job-fixed") == "job-fixed"


def test_new_id_is_read_from_the_name() -> None:
    assert re.fullmatch(r"job-fix-the-login-page-[0-9a-f]{4}", new_id("job", "Fix the login page!"))
    assert re.fullmatch(r"research-agents-t1-[0-9a-f]{4}", new_id("research", "agents/t1"))


def test_new_id_without_a_name_is_two_hex_groups() -> None:
    assert re.fullmatch(r"job-[0-9a-f]{4}-[0-9a-f]{4}", new_id("job", ""))


def test_new_id_cuts_a_long_name_to_the_slug_length() -> None:
    generated = new_id("job", "word " * 40)
    slug = generated.removeprefix("job-").rsplit("-", 1)[0]
    assert len(slug) <= settings.cli.slug_chars and not slug.endswith("-")


def test_run_refuses_a_provider_with_no_settings_table() -> None:
    result = CliRunner().invoke(app, ["run", "job", "hi", "--provider", "codex", "--detach"])
    assert result.exit_code == 1
    assert "provider 'codex' has no [providers.codex] table" in result.output
    assert "configured: claude, opencode" in result.output


def test_normalize_status_is_case_insensitive() -> None:
    assert normalize_status("running") == "Running"
    assert normalize_status("COMPLETED") == "Completed"
    assert normalize_status("TimedOut") == "TimedOut"


def test_normalize_status_rejects_unknown() -> None:
    with pytest.raises(typer.BadParameter, match="want one of"):
        normalize_status("bogus")


def test_normalize_workflow_type_is_case_insensitive() -> None:
    assert normalize_workflow_type("Job") == "job"
    assert normalize_workflow_type("DISTILL") == "distill"


def test_normalize_workflow_type_rejects_unknown() -> None:
    with pytest.raises(typer.BadParameter, match="want one of"):
        normalize_workflow_type("bogus")


def test_run_coro_turns_failures_into_exit() -> None:
    async def boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(typer.Exit) as failed:
        run_coro(boom())
    assert failed.value.exit_code == 1
