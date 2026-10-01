from itertools import batched
from pathlib import Path

from distill.boilerplate import SKIP_DIRS, strip_boilerplate
from distill.chunking import Chunk
from distill.settings.load import settings

BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".webp",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".whl",
        ".pyc",
        ".pyo",
        ".so",
        ".o",
        ".a",
        ".exe",
        ".dll",
        ".dylib",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".lock",
    }
)

ROOT_DOCS = frozenset(
    {
        "readme.md",
        "readme.rst",
        "readme.txt",
        "readme",
        "license",
        "license.md",
        "license.txt",
        "changelog.md",
        "contributing.md",
        "code_of_conduct.md",
        "pyproject.toml",
        "package.json",
        "cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "gemfile",
        "setup.py",
        "setup.cfg",
        "composer.json",
        "dune-project",
        "makefile",
        "justfile",
        "dockerfile",
        "docker-compose.yml",
    }
)


def chunk_repo(repo: Path, target: int) -> list[Chunk]:
    """One chunk per macro component of a cloned repo, overview chunk first."""
    pieces = _components(repo, target)
    if len(pieces) + 1 > settings.chunking.max_chunks:
        pieces = _merge_pieces(pieces, settings.chunking.max_chunks - 1)
    chunks = [Chunk(index=1, title="Overview", text=_overview(repo, [name for name, _ in pieces]))]
    chunks += [
        Chunk(index=i + 2, title=name, text=body.strip()) for i, (name, body) in enumerate(pieces)
    ]
    return chunks


def _components(repo: Path, target: int) -> list[tuple[str, str]]:
    """One (name, body) pair per top-level dir plus trailing top-level files."""
    pieces: list[tuple[str, str]] = []
    entries = sorted(
        (path for path in repo.iterdir() if path.name not in SKIP_DIRS),
        key=lambda path: path.name.lower(),
    )
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            body = _component_chunk(entry.name, entry, target)
            if body is not None:
                pieces.append((entry.name, body))
    blocks = [
        block
        for path in entries
        if path.is_file()
        and path.name.lower() not in ROOT_DOCS
        and path.suffix.lower() not in BINARY_SUFFIXES
        and (block := _file_block(path, repo, target)) is not None
    ]
    if blocks:
        pieces.append(
            (
                "top-level-files",
                f"# Component: top-level-files\n\n{len(blocks)} source files.\n"
                + "\n\n".join(blocks),
            )
        )
    return pieces


def _component_chunk(name: str, root: Path, target: int) -> str | None:
    """Chunk body for one top-level directory; None when it holds no text."""
    blocks = [
        block
        for path in _text_files(root)
        if (block := _file_block(path, root.parent, target)) is not None
    ]
    if not blocks:
        return None
    return f"# Component: {name}\n\n{len(blocks)} source files.\n" + "\n\n".join(blocks)


def _text_files(component: Path) -> list[Path]:
    """Text files under `component`, skipping binary suffixes and oversize files."""
    found = []
    for path in sorted(component.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > settings.repo.max_file_bytes:
                continue
        except OSError:
            continue
        found.append(path)
    return found


def _file_block(path: Path, anchor: Path, target: int) -> str | None:
    """One file as a headed fenced block; None when it is not readable text."""
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not text.strip():
        return None
    rel = path.relative_to(anchor).as_posix()
    lines = text.count("\n") + 1
    if len(text) > target:
        text = text[:target] + f"\n... (truncated, {len(text) - target} more characters)"
    return f"## {rel} ({lines} lines)\n\n```\n{text.strip()}\n```"


def _merge_pieces(pieces: list[tuple[str, str]], cap: int) -> list[tuple[str, str]]:
    """Merge neighbouring (name, body) pairs until at most `cap` remain."""
    while len(pieces) > cap:
        pieces = [_paired(batch) for batch in batched(pieces, 2, strict=False)]
    return pieces


def _paired(batch: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    """One pair merged, or the odd last piece as is."""
    if len(batch) == 1:
        return batch[0]
    return _joined(batch[0], batch[1])


def _joined(first: tuple[str, str], second: tuple[str, str]) -> tuple[str, str]:
    """Two neighbouring (name, body) pairs as one."""
    return (f"{first[0]}-and-{second[0]}", first[1] + "\n\n" + second[1])


def _overview(repo: Path, components: list[str]) -> str:
    """First chunk: what the repo is and which components follow."""
    lines = [f"# Overview: {repo.name}", ""]
    for readme in ("README.md", "README.rst", "README.txt", "README"):
        path = repo / readme
        if path.is_file():
            try:
                text = strip_boilerplate(
                    path.read_text(encoding="utf-8", errors="replace")[: settings.repo.readme_chars]
                )
            except OSError:
                text = ""
            if text.strip():
                lines += ["## README", "", text.strip(), ""]
            break
    lines += ["## Macro components", ""]
    lines += [f"- {name}/" for name in components] or ["- (no component directories)"]
    return "\n".join(lines).strip() + "\n"
