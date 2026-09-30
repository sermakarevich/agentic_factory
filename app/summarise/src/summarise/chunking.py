"""Split fetched source text into chapter-sized chunks along its own structure.

Pure text in, list of chunks out: the
text is cut at markdown headings when it has them, else at blank lines,
and neighbouring pieces are packed greedily up to a target size so every
chunk is a whole section (or a run of whole paragraphs), never a cut mid
sentence. Chunk count is capped so a very long source still yields a
workable number of wiki jobs.

`chunk_repo` is the codebase-track sibling: one chunk per macro component
(top-level package, module, service or tooling directory) of a cloned repo,
plus an overview chunk first, so each wiki job writes the page of one
real component instead of one slice of prose.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from summarise.settings.load import settings

_HEADING_RE = re.compile(r"^#{1,3} +\S", re.MULTILINE)
_TITLE_RE = re.compile(r"^#{1,3} +(.+?)\s*$", re.MULTILINE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

#: A text with fewer headings than this is split on blank lines instead.
_HEADINGS_TO_SPLIT_ON = 2
#: Neighbouring pieces are merged in pairs until the cap holds.
_PAIR = 2

#: Directories never treated as macro components and never descended into.
#: Version control, virtualenvs, dependency trees and build output carry no
#: design of their own; dot-directories are tooling config, not components.
REPO_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".tox",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        "target",
        ".idea",
        ".vscode",
    }
)

#: Suffixes never read into a component chunk: images, fonts, archives,
#: compiled artifacts and lockfiles (dependency pins, not design).
_REPO_BINARY_SUFFIXES = frozenset(
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

#: README boilerplate headings dropped before chunking (case-insensitive,
#: normalized match): sponsorship asks, stargazing, legal/meta sections and
#: nav — never the source's own argument. Kept narrow on purpose: "related
#: projects" is boilerplate but "related work" in a paper is not.
_BOILERPLATE_HEADINGS = frozenset(
    {
        "sponsor",
        "sponsors",
        "sponsorship",
        "acknowledgement",
        "acknowledgements",
        "acknowledgment",
        "acknowledgments",
        "star history",
        "stargazers",
        "stargazer",
        "license",
        "contributing",
        "contribution",
        "contributions",
        "citation",
        "citations",
        "cite",
        "citing",
        "code of conduct",
        "changelog",
        "table of contents",
        "related projects",
        "related project",
    }
)

#: Wiki page stems containing any of these came from README boilerplate, not
#: from the source's argument. Mirrors _BOILERPLATE_HEADINGS in slug form so
#: the verify stage rejects what the chunker should already have dropped.
BOILERPLATE_WIKI_SUBSTRINGS = (
    "sponsor",
    "acknowledgement",
    "acknowledgment",
    "star-history",
    "stargazer",
    "contributing",
    # not "contribution": papers name real sections "...-and-contributions".
    "citation",
    "citing",
    "code-of-conduct",
    "changelog",
    "table-of-contents",
    "related-project",
)

#: Markup that marks a section as badge/link chrome rather than prose.
_BADGE_MARKUP_RE = re.compile(r"!\[[^\]]*\]\(|<img\b|shields\.io|opencollective", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_IMAGE_RE = re.compile(r"\[?\![^\]]*\]\([^)]*\)")


def _normalize_heading(title: str) -> str:
    """Lowercase alphanumeric-words form of a heading for boilerplate matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", title.lower())).strip()


def is_boilerplate_heading(title: str) -> bool:
    """True when a section heading names README boilerplate, not content."""
    normalized = _normalize_heading(title)
    if not normalized:
        return False
    for boilerplate in _BOILERPLATE_HEADINGS:
        if normalized == boilerplate or normalized.startswith(boilerplate + " "):
            return True
    return False


def _substantive_chars(body: str) -> int:
    """Alphanumeric characters left after badge/image/link/HTML markup is gone."""
    text = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[#>*`\-_|:\[\]()!]", " ", text)
    return len(re.sub(r"\s+", "", text))


def _is_badges_only(section: str) -> bool:
    """True when a section is badge/link chrome with no substantive prose."""
    lines = section.splitlines()
    body = "\n".join(lines[1:]) if lines and lines[0].lstrip().startswith("#") else section
    if _substantive_chars(body) >= settings.chunking.badges_only_chars:
        return False
    if _BADGE_MARKUP_RE.search(section):
        return True
    content = [line for line in body.splitlines() if line.strip()]
    if not content:
        return True
    return all(
        re.fullmatch(r"\s*[-*+]?\s*(\[[^\]]*\]\([^)]*\)\s*)+", line) is not None for line in content
    )


def _section_heading(section: str) -> str | None:
    """The section's own `#`-heading text, else None."""
    match = re.match(r"\s*#{1,3} +(.+?)\s*$", section.splitlines()[0] if section else "")
    if match is not None:
        return match.group(1).strip("# ").strip()
    return None


def strip_boilerplate(text: str) -> str:
    """Drop README boilerplate sections; the substantive remainder stays ordered."""
    body = text.strip()
    if not body:
        return ""
    starts = [m.start() for m in _HEADING_RE.finditer(body)]
    if not starts:
        return "" if _is_badges_only(body) else body
    if starts[0] > 0:
        starts.insert(0, 0)
    kept = []
    for start, end in zip(starts, [*starts[1:], len(body)], strict=True):
        section = body[start:end]
        heading = _section_heading(section)
        if heading is not None and is_boilerplate_heading(heading):
            continue
        if _is_badges_only(section):
            continue
        kept.append(section)
    return "\n\n".join(kept).strip()


#: Root files folded into the overview chunk instead of their own component.
_REPO_ROOT_DOCS = frozenset(
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


@dataclass(frozen=True, slots=True)
class Chunk:
    """One contiguous piece of the source with a short human title."""

    index: int
    title: str
    text: str

    @property
    def slug(self) -> str:
        """Kebab-case file stem, e.g. `03-attention-mechanism`."""
        kebab = _SLUG_RE.sub("-", self.title.lower()).strip("-")
        base = kebab[: settings.chunking.slug_chars].strip("-") or "part"
        return f"{self.index:02d}-{base}"


def chunk_chars_in_bounds(value: int) -> int:
    """The requested target chunk size, raised or lowered to the bounds settings allow."""
    return max(settings.chunking.chars_min, min(settings.chunking.chars_max, value))


def _sections(text: str) -> list[str]:
    """Split on markdown headings when present, else on blank lines."""
    if len(_HEADING_RE.findall(text)) >= _HEADINGS_TO_SPLIT_ON:
        starts = [m.start() for m in _HEADING_RE.finditer(text)]
        if starts[0] > 0:
            starts.insert(0, 0)
        pieces = [text[a:b] for a, b in zip(starts, [*starts[1:], len(text)], strict=True)]
        return [p for p in pieces if p.strip()]
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pack(pieces: list[str], target: int) -> list[str]:
    """Greedily join neighbouring pieces up to `target` characters each."""
    packed: list[str] = []
    current = ""
    for piece in pieces:
        over_target = len(current) + len(piece) > target
        if current and over_target and len(current) >= settings.chunking.min_section_chars:
            packed.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        packed.append(current)
    return packed


def _split_long(piece: str, target: int) -> list[str]:
    """Cut one oversized piece at paragraph breaks so no chunk dwarfs the rest."""
    if len(piece) <= target * 2:
        return [piece]
    paragraphs = [p for p in re.split(r"\n\s*\n", piece) if p.strip()]
    if len(paragraphs) <= 1:
        return [piece]
    return _pack(paragraphs, target)


def _title_of(text: str, index: int) -> str:
    """Heading of the piece when it has one, else its first words.

    NUL bytes are stripped: a title derived from fetched text (e.g.
    `pdftotext` output with interleaved \\x00) ends up in prompts and
    database rows, where a NUL is refused.
    """
    match = _TITLE_RE.search(text)
    if match is not None:
        return match.group(1).strip("# ").strip().replace("\x00", "")
    words = text.strip().split()
    return " ".join(words[:6]).replace("\x00", "") if words else f"Part {index}"


def _merge_to_cap(pieces: list[str], cap: int) -> list[str]:
    """Merge neighbouring pieces pairwise until at most `cap` remain."""
    while len(pieces) > cap:
        merged: list[str] = []
        for i in range(0, len(pieces), 2):
            pair = pieces[i : i + 2]
            merged.append("\n\n".join(pair))
        pieces = merged
    return pieces


def chunk_text(text: str, target: int) -> list[Chunk]:
    """Cut `text` into structure-aligned chunks of roughly `target` characters.

    README boilerplate sections (Sponsor, License, Star History, ...) are
    dropped first; a source with nothing substantive left yields zero chunks
    so the workflow fails instead of filing chrome as knowledge.
    """
    body = strip_boilerplate(text)
    if not body:
        return []
    pieces: list[str] = []
    for section in _sections(body):
        pieces.extend(_split_long(section, target))
    packed = _merge_to_cap(_pack(pieces, target), settings.chunking.max_chunks)
    return [
        Chunk(index=i + 1, title=_title_of(piece, i + 1), text=piece.strip())
        for i, piece in enumerate(packed)
    ]


def _repo_files(component: Path) -> list[Path]:
    """Text files under `component`, skipping binary suffixes and oversize files."""
    found = []
    for path in sorted(component.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in _REPO_BINARY_SUFFIXES:
            continue
        if any(part in REPO_SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > settings.repo.max_file_bytes:
                continue
        except OSError:
            continue
        found.append(path)
    return found


def _repo_file_block(path: Path, anchor: Path, target: int) -> str | None:
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
    fence = "```"
    return f"## {rel} ({lines} lines)\n\n{fence}\n{text.strip()}\n{fence}"


def _repo_component_chunk(name: str, root: Path, target: int) -> str | None:
    """Chunk body for one top-level directory; None when it holds no text."""
    blocks = []
    for path in _repo_files(root):
        block = _repo_file_block(path, root.parent, target)
        if block is not None:
            blocks.append(block)
    if not blocks:
        return None
    head = f"# Component: {name}\n\n{len(blocks)} source files.\n"
    return head + "\n\n".join(blocks)


def chunk_repo(repo: Path, target: int) -> list[Chunk]:
    """One chunk per macro component of a cloned repo, overview chunk first.

    Components are the repo's top-level directories (minus VCS, venvs and
    build output); root-level source files outside the doc/manifest set form
    a trailing `top-level-files` component. Every chunk keeps whole files,
    each file capped at `target` characters so one giant generated file
    cannot dwarf the rest. Always returns at least the overview chunk, so a
    wiki step is never planned empty.
    """
    pieces: list[tuple[str, str]] = []
    entries = sorted(
        (p for p in repo.iterdir() if p.name not in REPO_SKIP_DIRS),
        key=lambda p: p.name.lower(),
    )
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            body = _repo_component_chunk(entry.name, entry, target)
            if body is not None:
                pieces.append((entry.name, body))
    root_files = [
        p
        for p in entries
        if p.is_file()
        and p.name.lower() not in _REPO_ROOT_DOCS
        and p.suffix.lower() not in _REPO_BINARY_SUFFIXES
    ]
    root_blocks = [
        block for path in root_files if (block := _repo_file_block(path, repo, target)) is not None
    ]
    if root_blocks:
        head = f"# Component: top-level-files\n\n{len(root_blocks)} source files.\n"
        pieces.append(("top-level-files", head + "\n\n".join(root_blocks)))
    if len(pieces) + 1 > settings.chunking.max_chunks:
        pieces = _merge_repo_pieces(pieces, settings.chunking.max_chunks - 1)
    overview = _repo_overview_chunk(repo, [name for name, _ in pieces])
    chunks = [Chunk(index=1, title="Overview", text=overview)]
    chunks += [
        Chunk(index=i + 2, title=name, text=body.strip()) for i, (name, body) in enumerate(pieces)
    ]
    return chunks


def _merge_repo_pieces(pieces: list[tuple[str, str]], cap: int) -> list[tuple[str, str]]:
    """Merge neighbouring (name, body) pairs until at most `cap` remain."""
    while len(pieces) > cap:
        merged: list[tuple[str, str]] = []
        for i in range(0, len(pieces), _PAIR):
            pair = pieces[i : i + _PAIR]
            if len(pair) == _PAIR:
                name = f"{pair[0][0]}-and-{pair[1][0]}"
                merged.append((name, pair[0][1] + "\n\n" + pair[1][1]))
            else:
                merged.append(pair[0])
        pieces = merged
    return pieces


def _repo_overview_chunk(repo: Path, components: list[str]) -> str:
    """First chunk: what the repo is and which components follow."""
    lines = [f"# Overview: {repo.name}", ""]
    for readme in ("README.md", "README.rst", "README.txt", "README"):
        path = repo / readme
        if path.is_file():
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                raw = raw[: settings.repo.readme_chars]
                text = strip_boilerplate(raw)
            except OSError:
                text = ""
            if text.strip():
                lines += ["## README", "", text.strip(), ""]
            break
    lines += ["## Macro components", ""]
    lines += [f"- {name}/" for name in components] or ["- (no component directories)"]
    return "\n".join(lines).strip() + "\n"
