"""The autocode activities: git, the repo's commands and the files on disk,
all run by code so no coder ever runs git or judges its own tests. Each is a
thin call into the `autocode` app; what cannot change on a retry (a dirty
tree, no repo, HEAD off the branch) fails at once."""

from pathlib import Path

from autocode.command import ran
from autocode.contract import Check, Commit, Ran
from autocode.git import DirtyTree, GitFailed, NotARepo, OffBranch, committed, on_branch
from autocode.lock import hashes
from autocode.old_tests import old_tests
from autocode.written import folders_without_tests, missing_files
from pydantic import BaseModel, Field
from temporalio import activity
from temporalio.exceptions import ApplicationError


class BranchRequest(BaseModel):
    repo: str
    feature: str
    timeout_sec: int


class CommitRequest(BaseModel):
    repo: str
    feature: str
    message: str
    timeout_sec: int


class CheckRequest(BaseModel):
    repo: str
    check: Check
    timeout_sec: int
    tail_chars: int


class PathsRequest(BaseModel):
    """Paths relative to the repo root: the files or folders a stage was to write."""

    repo: str
    paths: list[str]


class OldTestsRequest(BaseModel):
    repo: str
    test_dirs: list[str] = Field(description="The repo's test folders, relative to its root.")
    feature_dir: str = Field(description="Where the feature's tests land: tests/<feature>.")


class FolderRequest(BaseModel):
    repo: str
    folder: str = Field(description="Relative to the repo root.")


@activity.defn
async def autocode_branch(request: BranchRequest) -> str:
    """The feature branch checked out from a clean tree: its name."""
    try:
        return await on_branch(Path(request.repo), request.feature, request.timeout_sec)
    except (NotARepo, DirtyTree) as error:
        raise ApplicationError(str(error), type=type(error).__name__, non_retryable=True) from error
    except GitFailed as error:
        raise ApplicationError(str(error), type="GitFailed") from error


@activity.defn
async def autocode_commit(request: CommitRequest) -> Commit | None:
    """Everything in the work tree committed on the feature branch; None when nothing changed."""
    try:
        return await committed(
            Path(request.repo), request.feature, request.message, request.timeout_sec
        )
    except OffBranch as error:
        raise ApplicationError(str(error), type="OffBranch", non_retryable=True) from error
    except GitFailed as error:
        raise ApplicationError(str(error), type="GitFailed") from error


@activity.defn
async def autocode_check(request: CheckRequest) -> Ran:
    """One of the repo's commands run from its root: exit code and output's tail.
    A red or timed-out run is a result, not an error."""
    check = request.check
    return await ran(
        check.name, check.command, Path(request.repo), request.timeout_sec, request.tail_chars
    )


@activity.defn
async def autocode_missing_files(request: PathsRequest) -> list[str]:
    """The paths that are not a file in the repo."""
    return missing_files(Path(request.repo), request.paths)


@activity.defn
async def autocode_folders_without_tests(request: PathsRequest) -> list[str]:
    """The folders that hold no test file."""
    return folders_without_tests(Path(request.repo), request.paths)


@activity.defn
async def autocode_old_tests(request: OldTestsRequest) -> list[str]:
    """The test paths there were, without the feature's own folder."""
    return old_tests(Path(request.repo), request.test_dirs, request.feature_dir)


@activity.defn
async def autocode_test_hashes(request: FolderRequest) -> dict[str, str]:
    """The sha256 of every file under the folder, by its path inside it."""
    return hashes(Path(request.repo) / request.folder)
