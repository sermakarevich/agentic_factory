import re
from pathlib import Path

from distill.boilerplate import BOILERPLATE_WIKI_SUBSTRINGS
from distill.settings.load import settings

REQUIRED_FILES = (
    "index.md",
    "summary.md",
    "digest.md",
    "explainer.md",
    "questions.md",
    "critical_thinking.md",
)

BANNED_WIKI_SUBSTRINGS = (
    "latest-commit",
    "skip-to-content",
    "sign-in",
    *BOILERPLATE_WIKI_SUBSTRINGS,
)

LOCAL_ROOTS = frozenset(
    {"Users", "home", "root", "tmp", "var", "private", "Volumes", "mnt", "media", "opt"}
)

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def verify_research_dir(research_dir: Path) -> list[str]:
    """Check one finished entry; return one failure string per problem."""
    checks = (
        _required_files,
        _source,
        _wiki,
        _digest,
        _index_links,
    )
    return [problem for check in checks for problem in check(research_dir)]


def _required_files(research_dir: Path) -> list[str]:
    """Every derived file exists and is bigger than `verify.min_bytes`."""
    least = settings.verify.min_bytes
    failures = []
    for name in REQUIRED_FILES:
        path = research_dir / name
        if not path.is_file():
            failures.append(f"verify: missing {name}")
        elif path.stat().st_size <= least:
            failures.append(
                f"verify: {name} is trivial ({path.stat().st_size} bytes, need >{least})"
            )
    return failures


def _source(research_dir: Path) -> list[str]:
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


def _wiki(research_dir: Path) -> list[str]:
    """At least one wiki page; none named after site chrome."""
    pages = _wiki_pages(research_dir)
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


def _digest(research_dir: Path) -> list[str]:
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
        for path in _wiki_pages(research_dir)
        if path.stem not in text
    ]


def _index_links(research_dir: Path) -> list[str]:
    """Every link in index.md resolves to a file that exists."""
    index = research_dir / "index.md"
    if not index.is_file():
        return []
    try:
        text = index.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    targets = WIKILINK_RE.findall(text) + MD_LINK_RE.findall(text)
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


def _wiki_pages(research_dir: Path) -> list[Path]:
    """Wiki pages in order; empty when wiki/ is missing or has no pages."""
    wiki = research_dir / "wiki"
    if not wiki.is_dir():
        return []
    return sorted(
        (path for path in wiki.glob("*.md") if path.is_file()),
        key=lambda path: path.name,
    )


def _clean_target(raw: str) -> str:
    """Drop the anchor and the escape backslash an Obsidian table cell adds."""
    return raw.split("#", 1)[0].strip().rstrip("\\").strip()


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


def _is_outside_entry(target: str) -> bool:
    """True when the link points somewhere the entry does not own."""
    if target.startswith(("http://", "https://", "mailto:", "~")) or "://" in target:
        return True
    return target.startswith("/") and target.lstrip("/").split("/", 1)[0] in LOCAL_ROOTS
