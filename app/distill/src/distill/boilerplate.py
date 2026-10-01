import re

from distill.settings.load import settings

HEADING_RE = re.compile(r"^#{1,3} +\S", re.MULTILINE)

HEADINGS = frozenset(
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

SKIP_DIRS = frozenset(
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

BADGE_MARKUP_RE = re.compile(r"!\[[^\]]*\]\(|<img\b|shields\.io|opencollective", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_IMAGE_RE = re.compile(r"\[?\![^\]]*\]\([^)]*\)")


def is_boilerplate_heading(title: str) -> bool:
    """True when a heading names README boilerplate rather than content."""
    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", title.lower())).strip()
    if not normalized:
        return False
    return any(normalized == name or normalized.startswith(name + " ") for name in HEADINGS)


def strip_boilerplate(text: str) -> str:
    """Drop README boilerplate sections; the substantive remainder stays ordered."""
    body = text.strip()
    if not body:
        return ""
    starts = [match.start() for match in HEADING_RE.finditer(body)]
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


def _section_heading(section: str) -> str | None:
    """The section's own `#`-heading text, else None."""
    lines = section.splitlines()
    match = re.match(r"\s*#{1,3} +(.+?)\s*$", lines[0] if lines else "")
    if match is None:
        return None
    return match.group(1).strip("# ").strip()


def _is_badges_only(section: str) -> bool:
    """True when a section is badge/link chrome with no substantive prose."""
    lines = section.splitlines()
    body = "\n".join(lines[1:]) if lines and lines[0].lstrip().startswith("#") else section
    if _substantive_chars(body) >= settings.chunking.badges_only_chars:
        return False
    if BADGE_MARKUP_RE.search(section):
        return True
    content = [line for line in body.splitlines() if line.strip()]
    if not content:
        return True
    return all(
        re.fullmatch(r"\s*[-*+]?\s*(\[[^\]]*\]\([^)]*\)\s*)+", line) is not None for line in content
    )


def _substantive_chars(body: str) -> int:
    """Alphanumeric characters left after badge/image/link/HTML markup is gone."""
    text = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[#>*`\-_|:\[\]()!]", " ", text)
    return len(re.sub(r"\s+", "", text))
