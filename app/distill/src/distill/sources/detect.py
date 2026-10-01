import re
import urllib.parse
import urllib.request
from pathlib import Path

from distill.contract import SourceKind
from distill.sources.source import SourceError

YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")
X_HOSTS = ("x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com")
GITHUB_HOSTS = ("github.com", "www.github.com")
ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)")
LOCAL_TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})


def detect(url: str) -> SourceKind:
    """Pick the fetch route from the URL's host and path, or a local suffix."""
    local = local_path(url)
    if local is not None:
        return _detect_local(url, local)
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SourceError(f"url {url!r}: must be an http(s) URL or an absolute local path")
    host = parsed.netloc.lower()
    if host in YOUTUBE_HOSTS:
        return SourceKind.youtube
    if host in X_HOSTS:
        return SourceKind.x
    if repo_parts(url) is not None:
        return SourceKind.repo
    if ARXIV_ID_RE.search(url) or parsed.path.lower().endswith(".pdf"):
        return SourceKind.pdf
    return SourceKind.article


def local_path(url: str) -> Path | None:
    """Absolute local path for `file://` URLs and bare paths; None when not local."""
    text = url.strip()
    if text.startswith("file://"):
        return Path(urllib.request.url2pathname(text[len("file://") :])).expanduser()
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme == "" and parsed.path.startswith("/"):
        return Path(parsed.path).expanduser()
    if text.startswith(("/", "~/")):
        return Path(text).expanduser()
    return None


def repo_parts(url: str) -> tuple[str, str] | None:
    """(owner, repo) for a repo root or tree path; None for other GitHub pages."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.netloc.lower() not in GITHUB_HOSTS:
        return None
    match [segment for segment in parsed.path.split("/") if segment]:
        case [owner, repo]:
            return owner, repo.removesuffix(".git")
        case [owner, repo, "tree", _ref, *_]:
            return owner, repo.removesuffix(".git")
        case _:
            return None


def repo_root(url: str) -> tuple[str, str] | None:
    """(owner, repo) for a github.com repo landing page, else None."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None
    if parsed.netloc.lower() not in GITHUB_HOSTS:
        return None
    match [segment for segment in parsed.path.split("/") if segment]:
        case [owner, repo]:
            return owner, repo
        case _:
            return None


def _detect_local(url: str, local: Path) -> SourceKind:
    """Fetch route from a local file's suffix; junk suffixes are rejected loudly."""
    suffix = local.suffix.lower()
    if suffix == ".pdf":
        return SourceKind.pdf
    if suffix in LOCAL_TEXT_SUFFIXES:
        return SourceKind.article
    raise SourceError(f"url {url!r}: local files must be .pdf, .md or .txt")
