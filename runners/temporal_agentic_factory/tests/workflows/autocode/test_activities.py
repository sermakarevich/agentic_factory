"""The autocode activities against a real git repo in tmp_path: the branch
from a clean tree, a dirty tree refused for good, a commit skipped when
nothing changed; and a command's exit code, output's tail and timeout."""

import subprocess
from pathlib import Path

import pytest
from autocode.contract import Check, Commit, Ran
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from temporal_agentic_factory.workflows.autocode.activities import (
    BranchRequest,
    CheckRequest,
    CommitRequest,
    FolderRequest,
    PathsRequest,
    autocode_branch,
    autocode_check,
    autocode_commit,
    autocode_folders_without_tests,
    autocode_missing_files,
    autocode_test_hashes,
)

TIMEOUT = 30


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo on `main` with one commit and a clean tree."""
    folder = tmp_path / "repo"
    folder.mkdir()
    git(folder, "init", "--quiet", "--initial-branch=main")
    git(folder, "config", "user.email", "test@example.com")
    git(folder, "config", "user.name", "Test")
    (folder / "README.md").write_text("hello\n")
    git(folder, "add", "-A")
    git(folder, "commit", "--quiet", "-m", "start")
    return folder


async def branch(repo: Path, feature: str = "csv") -> str:
    request = BranchRequest(repo=str(repo), feature=feature, timeout_sec=TIMEOUT)
    return await ActivityEnvironment().run(autocode_branch, request)


async def commit(repo: Path, message: str) -> Commit | None:
    request = CommitRequest(repo=str(repo), feature="csv", message=message, timeout_sec=TIMEOUT)
    return await ActivityEnvironment().run(autocode_commit, request)


async def test_a_clean_tree_gets_the_feature_branch_and_local_kept_out(repo: Path) -> None:
    assert await branch(repo) == "autocode/csv"

    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "autocode/csv"
    assert ".local/" in (repo / ".git" / "info" / "exclude").read_text().splitlines()
    (repo / ".local").mkdir()
    (repo / ".local" / "notes.md").write_text("scratch")
    assert git(repo, "status", "--porcelain") == ""


async def test_a_branch_made_before_is_checked_out_again(repo: Path) -> None:
    await branch(repo)
    git(repo, "checkout", "--quiet", "main")

    assert await branch(repo) == "autocode/csv"
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "autocode/csv"
    exclude = (repo / ".git" / "info" / "exclude").read_text().splitlines()
    assert exclude.count(".local/") == 1


async def test_a_dirty_tree_is_refused_for_good(repo: Path) -> None:
    (repo / "README.md").write_text("changed\n")

    with pytest.raises(ApplicationError) as raised:
        await branch(repo)

    assert raised.value.type == "DirtyTree" and raised.value.non_retryable
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


async def test_a_folder_that_is_no_repo_is_refused_for_good(tmp_path: Path) -> None:
    with pytest.raises(ApplicationError) as raised:
        await branch(tmp_path)

    assert raised.value.type == "NotARepo" and raised.value.non_retryable


async def test_a_change_is_committed_and_nothing_changed_is_skipped(repo: Path) -> None:
    await branch(repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "REQUIREMENTS.md").write_text("# Requirements\n")

    made = await commit(repo, "autocode(csv): requirements")
    skipped = await commit(repo, "autocode(csv): failures")

    assert made is not None and skipped is None
    assert git(repo, "log", "-1", "--format=%H %s") == f"{made.sha} autocode(csv): requirements"
    assert git(repo, "rev-list", "--count", "HEAD") == "2"


async def test_a_commit_off_the_feature_branch_is_refused_for_good(repo: Path) -> None:
    (repo / "x.txt").write_text("x")

    with pytest.raises(ApplicationError) as raised:
        await commit(repo, "autocode(csv): requirements")

    assert raised.value.type == "OffBranch" and raised.value.non_retryable


async def check(repo: Path, command: str, timeout_sec: int = TIMEOUT, tail: int = 100) -> Ran:
    request = CheckRequest(
        repo=str(repo),
        check=Check(name="suite", command=command),
        timeout_sec=timeout_sec,
        tail_chars=tail,
    )
    return await ActivityEnvironment().run(autocode_check, request)


async def test_a_command_gives_its_exit_code_and_the_tail_of_its_output(repo: Path) -> None:
    ran = await check(repo, "echo out; echo err >&2; printf '%050d' 0; exit 3", tail=20)

    assert ran.exit_code == 3 and not ran.green and not ran.timed_out
    assert ran.tail == "0" * 20


async def test_a_command_runs_in_the_repo_and_green_is_exit_zero(repo: Path) -> None:
    ran = await check(repo, "cat README.md")

    assert ran.green and ran.tail == "hello\n"


async def test_a_command_past_its_timeout_is_killed_and_keeps_what_it_printed(
    repo: Path,
) -> None:
    ran = await check(repo, "echo started; sleep 30", timeout_sec=1)

    assert ran.timed_out and not ran.green
    assert ran.tail == "started\n"


async def test_the_files_a_stage_wrote_are_checked(repo: Path) -> None:
    (repo / "tests" / "csv" / "R1").mkdir(parents=True)
    (repo / "tests" / "csv" / "R1" / "test_export.py").write_text("def test(): pass\n")
    env = ActivityEnvironment()

    missing = await env.run(
        autocode_missing_files, PathsRequest(repo=str(repo), paths=["README.md", "docs/R1.md"])
    )
    empty = await env.run(
        autocode_folders_without_tests,
        PathsRequest(repo=str(repo), paths=["tests/csv/R1", "tests/csv/main"]),
    )
    hashes = await env.run(autocode_test_hashes, FolderRequest(repo=str(repo), folder="tests/csv"))

    assert missing == ["docs/R1.md"] and empty == ["tests/csv/main"]
    assert list(hashes) == ["R1/test_export.py"]
