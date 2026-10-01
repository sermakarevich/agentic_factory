import os
import shutil
import subprocess
from pathlib import Path

from distill.boilerplate import SKIP_DIRS, strip_boilerplate
from distill.contract import SourceKind
from distill.settings.load import settings
from distill.sources.article import fetch as fetch_article
from distill.sources.detect import repo_parts
from distill.sources.source import Source, SourceError

MANIFESTS = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "setup.py",
    "setup.cfg",
    "composer.json",
    "dune-project",
)
READMES = ("README.md", "README.rst", "README.txt", "README")


def fetch(url: str, work_dir: Path) -> Source:
    """Shallow-clone a GitHub repo; the overview is the text."""
    parts = repo_parts(url)
    if parts is None:
        raise SourceError(f"fetch {url}: not a GitHub repository root or tree URL")
    if shutil.which("git") is None:
        return fetch_article(url, work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    dest = work_dir / "repo"
    if dest.exists():
        shutil.rmtree(dest)
    clone_url = f"https://github.com/{parts[0]}/{parts[1]}.git"
    argv = ["git", "clone", "--depth", "1", clone_url, str(dest)]
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=settings.fetch.cli_timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SourceError(f"repo: `{' '.join(argv)}` timed out", transient=True) from None
    except OSError as exc:
        raise SourceError(
            f"repo: `{' '.join(argv)}` could not start: {exc}", transient=True
        ) from None
    if done.returncode != 0:
        return fetch_article(url, work_dir)
    return Source(
        url=url,
        kind=SourceKind.repo,
        title=f"{parts[0]}/{parts[1]}",
        text=_overview(parts[0], parts[1], dest, _sha(dest)),
        tool="git-clone",
    )


def _sha(dest: Path) -> str:
    """HEAD sha of a fresh clone; 'unknown' when even that lookup fails."""
    try:
        done = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=settings.fetch.http_timeout_sec,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "unknown"
    sha = done.stdout.strip()
    return sha if done.returncode == 0 and sha else "unknown"


def _overview(owner: str, repo: str, dest: Path, sha: str) -> str:
    """Provenance plus README, manifests and tree: the Source text of a clone."""
    sections = [f"# {owner}/{repo}", "", f"Commit: {sha}", ""]
    for readme in READMES:
        path = dest / readme
        if path.is_file():
            sections += [
                "## README",
                "",
                strip_boilerplate(_capped(path, settings.repo.readme_chars)),
                "",
            ]
            break
    for manifest in MANIFESTS:
        path = dest / manifest
        if path.is_file():
            sections += [
                "## " + manifest,
                "",
                "```",
                _capped(path, settings.repo.manifest_chars),
                "```",
                "",
            ]
    sections += ["## Top-level layout", "", _tree(dest)]
    return "\n".join(sections).strip() + "\n"


def _capped(path: Path, cap: int) -> str:
    """File text up to `cap` characters, with a truncation marker past it."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > cap:
        return text[:cap] + f"\n\n... (truncated, {len(text) - cap} more characters)"
    return text


def _tree(dest: Path) -> str:
    """One line per top-level entry: kind, file count and line count."""
    rows = []
    for entry in sorted(dest.iterdir(), key=lambda p: p.name.lower()):
        if entry.name == ".git":
            continue
        if entry.is_dir() and not entry.is_symlink():
            files, lines = _count_tree(entry)
            rows.append(f"- {entry.name}/ (dir, {files} files, ~{lines} lines)")
        elif entry.is_file():
            rows.append(f"- {entry.name} (~{_count_lines(entry)} lines)")
    return "\n".join(rows) if rows else "(empty repository)"


def _count_tree(root: Path) -> tuple[int, int]:
    """(text files, lines) under `root`, skipping VCS and build output."""
    files = 0
    lines = 0
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            files += 1
            if files > settings.repo.tree_files_cap:
                return files, lines
            lines += _count_lines(Path(current) / name)
    return files, lines


def _count_lines(path: Path) -> int:
    """Newline count of a text file; 0 when it cannot be read as text."""
    try:
        if path.stat().st_size > settings.fetch.max_bytes:
            return 0
        with path.open(encoding="utf-8", errors="strict") as handle:
            return sum(1 for _ in handle)
    except (OSError, ValueError, UnicodeDecodeError):
        return 0
