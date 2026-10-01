"""The git a run needs: its feature branch from a clean tree, and commits
on it. Never a push: the branch stays local for a person to review."""

import asyncio
from pathlib import Path

from autocode.contract import Commit

BRANCH_PREFIX = "autocode/"  # the feature branch is autocode/<feature>
EXCLUDED = ".local/"  # the folder coders keep scratch files in, never committed


class GitFailed(Exception):
    """A git command exited non-zero or ran past its timeout."""


class NotARepo(Exception):
    """The folder is not inside a git work tree."""


class DirtyTree(Exception):
    """The work tree has uncommitted changes, so a run would mix them in."""


class OffBranch(Exception):
    """HEAD is not on the feature branch, so a commit would land elsewhere."""


def branch_of(feature: str) -> str:
    return f"{BRANCH_PREFIX}{feature}"


async def on_branch(repo: Path, feature: str, timeout_sec: float) -> str:
    """The feature branch checked out: made from the current branch, or the
    one a run before made. The repo must be clean; `.local/` is kept out of
    git through `.git/info/exclude`."""
    if not repo.is_dir() or await _exit_code(
        repo, timeout_sec, "rev-parse", "--is-inside-work-tree"
    ):
        raise NotARepo(f"{repo} is not a git repo")
    changes = await _git(repo, timeout_sec, "status", "--porcelain")
    if changes.strip():
        raise DirtyTree(f"{repo} has uncommitted changes:\n{changes}")
    branch = branch_of(feature)
    exists = not await _exit_code(
        repo, timeout_sec, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"
    )
    await _git(repo, timeout_sec, *(["checkout", branch] if exists else ["checkout", "-b", branch]))
    await _exclude_local(repo, timeout_sec)
    return branch


async def committed(repo: Path, feature: str, message: str, timeout_sec: float) -> Commit | None:
    """Everything in the work tree committed on the feature branch as
    `message`; None when nothing changed, so no empty commit is made."""
    head = (await _git(repo, timeout_sec, "rev-parse", "--abbrev-ref", "HEAD")).strip()
    if head != branch_of(feature):
        raise OffBranch(f"{repo} is on {head!r}, not {branch_of(feature)!r}")
    await _git(repo, timeout_sec, "add", "-A")
    if not await _exit_code(repo, timeout_sec, "diff", "--cached", "--quiet"):
        return None
    await _git(repo, timeout_sec, "commit", "--quiet", "--no-verify", "-m", message)
    sha = (await _git(repo, timeout_sec, "rev-parse", "HEAD")).strip()
    return Commit(sha=sha, message=message)


async def _exclude_local(repo: Path, timeout_sec: float) -> None:
    """`.local/` added to the repo's own exclude file, once."""
    exclude = (
        repo / (await _git(repo, timeout_sec, "rev-parse", "--git-path", "info/exclude")).strip()
    )
    lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    if EXCLUDED not in lines:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("\n".join([*lines, EXCLUDED]) + "\n", encoding="utf-8")


async def _git(repo: Path, timeout_sec: float, *args: str) -> str:
    """The output of `git <args>` in `repo`; GitFailed when it exits non-zero."""
    exit_code, output = await _run(repo, timeout_sec, *args)
    if exit_code:
        raise GitFailed(f"git {' '.join(args)} exited {exit_code}: {output.strip()}")
    return output


async def _exit_code(repo: Path, timeout_sec: float, *args: str) -> int:
    """The exit code of `git <args>` in `repo`, for the commands that answer by it."""
    exit_code, _ = await _run(repo, timeout_sec, *args)
    return exit_code


async def _run(repo: Path, timeout_sec: float, *args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=repo,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout_sec)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise GitFailed(f"git {' '.join(args)} ran past {timeout_sec}s") from None
    return process.returncode or 0, output.decode("utf-8", errors="replace")
