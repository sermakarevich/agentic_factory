import html
import re

from distill.boilerplate import is_boilerplate_heading
from distill.contract import SourceKind
from distill.settings.load import settings
from distill.sources.html import MarkdownExtractor, SubtreeExtractor
from distill.sources.http import get
from distill.sources.source import Source, SourceError

RAW_HOST = "raw.githubusercontent.com"
README_REFS = ("HEAD", "main", "master")
NOISE_RE = re.compile(r"(?i)skip to content|you signed in with another tab or window")
CHROME_HEADING_RE = re.compile(r"(?m)^#{1,4}\s+latest commit\b", re.IGNORECASE)


def fetch(url: str, owner: str, repo: str, body: bytes) -> Source:
    """A repo landing page as its README, never as the surrounding page chrome."""
    raw = _raw_readme(owner, repo)
    if raw is not None:
        return Source(
            url=url,
            kind=SourceKind.article,
            title=readme_title(raw, owner, repo),
            text=raw,
            tool="raw-github",
        )
    scoped = readme_text(body)
    if len(scoped) >= settings.fetch.min_text_chars and not CHROME_HEADING_RE.search(scoped):
        return Source(
            url=url,
            kind=SourceKind.article,
            title=readme_title(scoped, owner, repo),
            text=scoped,
            tool="urllib",
        )
    description = meta_description(body.decode("utf-8", errors="replace"))
    text = f"# {owner}/{repo}\n"
    if description:
        text += f"\n{description}\n"
    text += f"\nRepository: {url}\nNo README found for this repository."
    return Source(
        url=url, kind=SourceKind.article, title=f"{owner}/{repo}", text=text, tool="urllib"
    )


def readme_title(text: str, owner: str, repo: str) -> str:
    """First substantive README heading, else `owner/repo`."""
    for match in re.finditer(r"^#{1,3} +(.+?)\s*$", text, re.MULTILINE):
        title = match.group(1).strip("# ").strip()
        if title and not is_boilerplate_heading(title):
            return title[: settings.fetch.title_chars]
    return f"{owner}/{repo}"


def readme_text(body: bytes) -> str:
    """Markdown of the landing page's `#readme` (else first `article`) subtree."""
    probe = SubtreeExtractor()
    probe.feed(body.decode("utf-8", errors="replace"))
    subtree = probe.subtree()
    if subtree is None:
        return ""
    parser = MarkdownExtractor()
    parser.feed(subtree)
    lines = [line for line in parser.text().splitlines() if not NOISE_RE.search(line.strip())]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def meta_description(page: str) -> str:
    """The page's meta description (usually the repo tagline), else empty."""
    for match in re.finditer(r"<meta\s[^>]*>", page, re.IGNORECASE):
        attrs = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', match.group(0)))
        name = f"{attrs.get('name', '')} {attrs.get('property', '')}".lower()
        if "description" in name and attrs.get("content", "").strip():
            return html.unescape(attrs["content"].strip())
    return ""


def _raw_readme(owner: str, repo: str) -> str | None:
    """README.md off raw.githubusercontent.com; None when no ref has one."""
    for ref in README_REFS:
        try:
            body, _ = get(f"https://{RAW_HOST}/{owner}/{repo}/{ref}/README.md")
        except SourceError as exc:
            if exc.transient:
                raise
            continue
        text = body.decode("utf-8", errors="replace").strip()
        if text:
            return text
    return None
