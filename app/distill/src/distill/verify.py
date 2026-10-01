"""Verify a finished distill knowledge-base entry against the recipe.

Run after the index job, on the entry folder the plan job named. Pure
function in, list of problem strings out, so the same logic is
unit-testable:

- index/summary/digest/explainer/questions/critical_thinking exist and are
  non-trivial (more than `verify.min_bytes` bytes).
- source/source.md exists and carries the ``Source:`` provenance line.
- wiki/ holds at least one page and no page stemmed from site chrome or
  README boilerplate.
- digest.md mentions every wiki page name (cheap proxy: each page's
  "In one sentence" line was quoted into the digest verbatim).
- every link in index.md resolves to a file that exists. Links that point
  outside the entry (http/mailto, ``~/...`` and machine-absolute paths
  such as ``/Users/me/Downloads/x.pdf``) are the operator's business,
  not the entry's, and are skipped.

An empty list means the entry passes; each string is one problem the
index job is asked to fix.
"""

import re
from pathlib import Path

from distill.chunking import BOILERPLATE_WIKI_SUBSTRINGS
from distill.settings.load import settings

#: Required derived files at the entry root (ai:summary:get recipe).
REQUIRED_FILES = (
    "index.md",
    "summary.md",
    "digest.md",
    "explainer.md",
    "questions.md",
    "critical_thinking.md",
)

#: Wiki page stems containing any of these came from site chrome
#: (GitHub nav, sign-in walls) or README boilerplate (Sponsor, License,
#: Star History, ...), not from the source's argument.
BANNED_WIKI_SUBSTRINGS = (
    "latest-commit",
    "skip-to-content",
    "sign-in",
    *BOILERPLATE_WIKI_SUBSTRINGS,
)

#: Leading segments that mark a link to a file on the operator's own disk
#: (``/Users/me/Downloads/x.pdf``) rather than an entry-relative root link
#: (``/wiki/01-overview.md``). Those live outside the entry, so verify
#: skips them instead of blocking the run.
_LOCAL_ROOTS = frozenset(
    {"Users", "home", "root", "tmp", "var", "private", "Volumes", "mnt", "media", "opt"}
)

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def verify_research_dir(research_dir: Path) -> list[str]:
    """Check one finished entry; return one failure string per problem."""
    failures: list[str] = []
    failures.extend(_check_required_files(research_dir))
    failures.extend(_check_source(research_dir))
    wiki_pages = _wiki_pages(research_dir)
    failures.extend(_check_wiki(research_dir, wiki_pages))
    failures.extend(_check_digest(research_dir, wiki_pages))
    failures.extend(_check_index_links(research_dir))
    return failures


def _check_required_files(research_dir: Path) -> list[str]:
    """Every derived file exists and is bigger than `verify.min_bytes`."""
    failures = []
    least = settings.verify.min_bytes
    for name in REQUIRED_FILES:
        path = research_dir / name
        if not path.is_file():
            failures.append(f"verify: missing {name}")
        elif path.stat().st_size <= least:
            size = path.stat().st_size
            failures.append(f"verify: {name} is trivial ({size} bytes, need >{least})")
    return failures


def _check_source(research_dir: Path) -> list[str]:
    """source/source.md exists and carries the `Source:` provenance line."""
    path = research_dir / "source" / "source.md"
    if not path.is_file():
        return ["verify: missing source/source.md"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"verify: cannot read source/source.md ({exc})"]
    if not re.search(r"(?m)^Source:\s*\S", text):
        return ["verify: source/source.md has no `Source:` provenance line"]
    return []


def _wiki_pages(research_dir: Path) -> list[Path]:
    """Wiki pages in order; empty when wiki/ is missing or has no pages."""
    wiki = research_dir / "wiki"
    if not wiki.is_dir():
        return []
    return sorted(
        (path for path in wiki.glob("*.md") if path.is_file()),
        key=lambda path: path.name,
    )


def _check_wiki(research_dir: Path, pages: list[Path]) -> list[str]:
    """At least one wiki page; none named after site chrome."""
    _ = research_dir
    if not pages:
        return ["verify: wiki/ holds no pages"]
    failures = []
    for path in pages:
        stem = path.stem.lower()
        for banned in BANNED_WIKI_SUBSTRINGS:
            if banned in stem:
                failures.append(f"verify: wiki page {path.name} looks like site chrome ({banned})")
                break
    return failures


def _check_digest(research_dir: Path, pages: list[Path]) -> list[str]:
    """digest.md mentions every wiki page name (rungs actually differ)."""
    digest = research_dir / "digest.md"
    if not digest.is_file():
        return []
    try:
        text = digest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [
        f"verify: digest.md never mentions wiki page {path.name}"
        for path in pages
        if path.stem not in text
    ]


def _clean_target(raw: str) -> str:
    """Drop the anchor and the markdown escape backslash a table cell adds.

    Obsidian needs the pipe escaped inside a table, so index.md carries
    ``[[wiki/01-overview\\|Overview]]``; the capture keeps that backslash.
    """
    return raw.split("#", 1)[0].strip().rstrip("\\").strip()


def _is_outside_entry(target: str) -> bool:
    """True when the link points somewhere the entry does not own."""
    if target.startswith(("http://", "https://", "mailto:", "~")) or "://" in target:
        return True
    # /Users/me/Downloads/x.pdf is the operator's own file; /wiki/01-overview.md
    # is an entry-relative root link and stays checked.
    return target.startswith("/") and target.lstrip("/").split("/", 1)[0] in _LOCAL_ROOTS


def _resolve_target(research_dir: Path, raw: str) -> Path | None:
    """Resolve one link target under the entry; None when external/anchor."""
    target = _clean_target(raw)
    if not target or _is_outside_entry(target):
        return None
    candidate = (research_dir / target.lstrip("/")).resolve()
    try:
        candidate.relative_to(research_dir.resolve())
    except ValueError:
        return None
    if candidate.suffix:
        return candidate
    dotted = candidate.with_suffix(".md")
    if dotted.is_file():
        return dotted
    return candidate


def _check_index_links(research_dir: Path) -> list[str]:
    """Every link in index.md resolves to a file that exists."""
    index = research_dir / "index.md"
    if not index.is_file():
        return []
    try:
        text = index.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    targets = _WIKILINK_RE.findall(text) + _MD_LINK_RE.findall(text)
    failures = []
    seen: set[str] = set()
    for raw in targets:
        target = _clean_target(raw)
        if not target or target in seen:
            continue
        seen.add(target)
        resolved = _resolve_target(research_dir, raw)
        if resolved is None:
            continue
        if not resolved.is_file():
            failures.append(f"verify: index.md links to missing {target}")
    return failures
