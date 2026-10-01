"""Fetch the text behind a URL.

One function per source kind, chosen
from the URL alone (`detect`): YouTube through the `yt` CLI, X/Twitter
through the `x` CLI, PDFs (including arXiv) through `pdftotext`, anything
else as a web page stripped to text with the standard library. A
github.com repo landing page fetches the repo README from
raw.githubusercontent.com first (falling back to the page's `#readme` /
`article` element, then to a repo-named stub) so page chrome never becomes
a "Latest commit" chunk. Every subprocess carries a timeout; every failure
surfaces as `SourceError` with the route that was tried and whether a
retry could help, so the workflow fails at its first step instead of
writing pages about a source nobody could read.
"""

import html
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path

from distill.chunking import REPO_SKIP_DIRS, is_boilerplate_heading, strip_boilerplate
from distill.settings.load import settings
from distill.settings.model import ThrottleSettings

_HTTP_NOT_ACCEPTABLE = 406
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR = 500

_YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")
_X_HOSTS = ("x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com")
_GITHUB_HOSTS = ("github.com", "www.github.com")
#: Repo roots on those hosts are cloned; other GitHub pages stay articles.
_GITHUB_RAW_HOST = "raw.githubusercontent.com"
#: Refs tried in order for a repo README; HEAD tracks the default branch.
_GITHUB_README_REFS = ("HEAD", "main", "master")
#: `github.com/<owner>/<repo>`: the two path segments of a repo root.
_REPO_ROOT_SEGMENTS = 2
#: `github.com/<owner>/<repo>/tree/<ref>`: at least this many segments name a tree.
_REPO_TREE_SEGMENTS = 4
#: Lines the scoped GitHub extractor drops even when they survive scoping.
_GITHUB_NOISE_RE = re.compile(r"(?i)skip to content|you signed in with another tab or window")
#: A scoped page that still opens on the commit widget is chrome, not a README.
_GITHUB_CHROME_HEADING_RE = re.compile(r"(?m)^#{1,4}\s+latest commit\b", re.IGNORECASE)
_ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)")
_LOCAL_TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "blockquote", "pre"}
)
_HEADING_TAGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}

#: (pattern, transient, message) read out of a CLI's whole output. A rich
#: traceback ends in boilerplate ("...no open issues which already describe
#: your problem!"), so the last line is a useless detail; these say what
#: actually went wrong and whether the URL deserves another try.
_CLI_CAUSES: tuple[tuple[re.Pattern[str], bool, str], ...] = (
    (
        re.compile(r"IpBlocked|RequestBlocked|blocking requests from your IP", re.IGNORECASE),
        True,
        "YouTube is blocking this machine's IP (too many requests); retry later",
    ),
    (
        re.compile(r"\b429\b|too many requests|rate.?limit", re.IGNORECASE),
        True,
        "rate limited by the server; retry later",
    ),
    (
        re.compile(r"PoTokenRequired", re.IGNORECASE),
        True,
        "YouTube asked for a proof-of-origin token; retry later",
    ),
    (
        re.compile(r"\b5\d\d\b|temporarily unavailable|service unavailable", re.IGNORECASE),
        True,
        "the server failed temporarily; retry later",
    ),
    # Measured 2026-09-22: a video whose transcript was fetched minutes
    # earlier reports "transcripts are disabled", and so does a control
    # video with known captions. While YouTube is rate-limiting a machine
    # it hides the caption tracks, so these two mean "disabled, or blocked
    # and unable to tell". Treating them as permanent would write a good
    # source off exactly when the block is on, so they are transient and
    # the caller's retry budget decides when to give up.
    (
        re.compile(r"transcripts are disabled|NoTranscriptFound|no transcript", re.IGNORECASE),
        True,
        "no transcript offered (the video has none, or YouTube is hiding them); retry later",
    ),
    (
        re.compile(r"VideoUnavailable|video unavailable|\b404\b|not found", re.IGNORECASE),
        False,
        "the source is gone (404 / unavailable)",
    ),
)


class SourceError(Exception):
    """The source behind a URL could not be fetched or read.

    ``transient`` marks a failure that says nothing about the source: a
    rate limit, an IP block, a timeout, a server-side 5xx. The same URL
    is likely to work later, so callers retry it instead of writing the
    source off. A dead link, a disabled transcript or an empty page is
    permanent and leaves ``transient`` false.
    """

    def __init__(self, message: str, *, transient: bool = False) -> None:
        """Remember the message and whether retrying could help."""
        super().__init__(message)
        self.transient = transient


class SourceKind(StrEnum):
    """Which route fetches a URL."""

    youtube = "youtube"
    x = "x"
    pdf = "pdf"
    article = "article"
    repo = "repo"


#: Manifest files read into a cloned repo's overview, first match wins per name.
_REPO_MANIFESTS = (
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
_REPO_READMES = ("README.md", "README.rst", "README.txt", "README")


@dataclass(frozen=True, slots=True)
class Source:
    """Fetched source: its kind, a title hint and the full text as markdown."""

    url: str
    kind: SourceKind
    title: str
    text: str
    tool: str


def _title(text: str) -> str:
    """A title cut to the length settings allow."""
    return text[: settings.fetch.title_chars]


def _local_path(url: str) -> Path | None:
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


def _github_repo_parts(url: str) -> tuple[str, str] | None:
    """(owner, repo) when `url` names a repo root or a tree path; None otherwise.

    A bare `github.com/<owner>/<repo>` root and any `/tree/...` path mean
    "analyze the codebase". Every other github.com path (blob, issues,
    pulls, ...), gists, and `*.github.io` Pages sites are single documents
    and stay on the article track.
    """
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.netloc.lower()
    if host in _GITHUB_HOSTS:
        parts = [segment for segment in parsed.path.split("/") if segment]
        if len(parts) == _REPO_ROOT_SEGMENTS:
            return parts[0], parts[1].removesuffix(".git")
        if len(parts) >= _REPO_TREE_SEGMENTS and parts[2] == "tree":
            return parts[0], parts[1].removesuffix(".git")
        return None
    return None


def _detect_local(url: str, local: Path) -> SourceKind:
    """Fetch route from a local file's suffix; junk suffixes are rejected loudly."""
    suffix = local.suffix.lower()
    if suffix == ".pdf":
        return SourceKind.pdf
    if suffix in _LOCAL_TEXT_SUFFIXES:
        return SourceKind.article
    raise SourceError(f"url {url!r}: local files must be .pdf, .md or .txt")


def detect(url: str) -> SourceKind:
    """Pick the fetch route from the URL's host and path, or from a local file suffix."""
    local = _local_path(url)
    if local is not None:
        return _detect_local(url, local)
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SourceError(f"url {url!r}: must be an http(s) URL or an absolute local path")
    host = parsed.netloc.lower()
    if host in _YOUTUBE_HOSTS:
        return SourceKind.youtube
    if host in _X_HOSTS:
        return SourceKind.x
    if _github_repo_parts(url) is not None:
        return SourceKind.repo
    if _ARXIV_ID_RE.search(url) or parsed.path.lower().endswith(".pdf"):
        return SourceKind.pdf
    return SourceKind.article


def _sanitize(source: Source) -> Source:
    """Drop NUL characters from a fetched source's title and text.

    `pdftotext -layout` interleaves \\x00 bytes into its output for some
    PDFs (symbol/table font regions), and NUL bytes can arrive in any
    decoded body. Neither a database column nor a prompt may carry one,
    so they are stripped here, once, for every fetch route.
    """
    if "\x00" not in source.title and "\x00" not in source.text:
        return source
    return replace(
        source,
        title=source.title.replace("\x00", ""),
        text=source.text.replace("\x00", ""),
    )


def fetch(url: str, work_dir: Path) -> Source:
    """Fetch one URL by its detected route; `work_dir` receives downloads."""
    local = _local_path(url)
    if local is not None:
        return _sanitize(_fetch_local_file(url, local, detect(url), work_dir))
    kind = detect(url)
    if kind is SourceKind.youtube:
        return _sanitize(_fetch_youtube(url))
    if kind is SourceKind.x:
        return _sanitize(_fetch_x(url))
    if kind is SourceKind.pdf:
        return _sanitize(_fetch_pdf(url, work_dir))
    if kind is SourceKind.repo:
        return _sanitize(_fetch_repo(url, work_dir))
    return _sanitize(_fetch_article(url))


def _fetch_local_file(url: str, path: Path, kind: SourceKind, work_dir: Path) -> Source:
    """Read a local file straight off disk: PDFs through pdftotext, text as-is."""
    if not path.is_file():
        raise SourceError(f"fetch {url}: no such file")
    if path.stat().st_size > settings.fetch.max_bytes:
        raise SourceError(f"fetch {url}: file exceeds {settings.fetch.max_bytes} bytes")
    work_dir.mkdir(parents=True, exist_ok=True)
    staged = work_dir / f"source{path.suffix.lower()}"
    if path.resolve() != staged.resolve():
        staged.write_bytes(path.read_bytes())
    if kind is SourceKind.pdf:
        if shutil.which("pdftotext") is None:
            raise SourceError("pdf: `pdftotext` (poppler) is not installed")
        text = _run(["pdftotext", "-layout", str(staged), "-"], what="pdf text")
        title = _pdf_title(staged, text)
        return Source(url=url, kind=kind, title=title, text=text, tool="pdftotext")
    text = staged.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < settings.fetch.min_text_chars:
        raise SourceError(f"fetch {url}: file yielded only {len(text)} characters of text")
    first = next((line.strip() for line in text.splitlines() if line.strip()), path.name)
    return Source(url=url, kind=kind, title=_title(first), text=text, tool="local-file")


def throttle_limit(kind: str | None) -> ThrottleSettings | None:
    """How many fetches of this kind may run at once and the gap between
    two, from settings; None for a kind that is not held back."""
    if kind == SourceKind.youtube:
        return settings.fetch.throttle.youtube
    if kind == SourceKind.x:
        return settings.fetch.throttle.x
    return None


class _Gate:
    """The slots of one throttled kind and when its last fetch started."""

    def __init__(self, limit: ThrottleSettings) -> None:
        self.slots = threading.Semaphore(limit.at_once)
        self.clock = threading.Lock()
        self.last_started = 0.0
        self.gap_sec = limit.gap_sec


class _Throttle:
    """Cap how many fetches of one kind run at once, and space them out.

    Many workflows fetch at the same time in one runner process, and each
    fetch shells out to a CLI, so without this the CLIs hit one host as
    fast as the runner allows. Shared process-wide; a fetch of an unlisted
    kind is not held back at all.
    """

    def __init__(self) -> None:
        """Start with no gates; each kind gets one the first time it is used."""
        self._guard = threading.Lock()
        self._gates: dict[str, _Gate] = {}

    def _gate(self, kind: str) -> _Gate | None:
        limit = throttle_limit(kind)
        if limit is None:
            return None
        with self._guard:
            gate = self._gates.get(kind)
            if gate is None:
                gate = _Gate(limit)
                self._gates[kind] = gate
            return gate

    @contextmanager
    def hold(self, kind: str | None) -> Iterator[None]:
        """Wait for a slot of this kind, and for the gap since the last one."""
        gate = self._gate(kind) if kind is not None else None
        if gate is None:
            yield
            return
        with gate.slots:
            with gate.clock:
                wait = gate.last_started + gate.gap_sec - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                gate.last_started = time.monotonic()
            yield


_THROTTLE = _Throttle()


def _cli_failure(what: str, argv: list[str], output: str, returncode: int) -> SourceError:
    """Name the cause in a CLI's output and say whether a retry could help."""
    for pattern, transient, message in _CLI_CAUSES:
        if pattern.search(output):
            return SourceError(f"{what}: `{' '.join(argv)}` failed: {message}", transient=transient)
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    tail = lines[-1] if lines else f"exit {returncode}"
    return SourceError(f"{what}: `{' '.join(argv)}` failed: {tail}")


def _run(argv: list[str], *, what: str, kind: str | None = None) -> str:
    """Run one CLI and return stdout; missing binary or failure is a SourceError."""
    if shutil.which(argv[0]) is None:
        raise SourceError(f"{what}: `{argv[0]}` is not installed or not on PATH")
    try:
        with _THROTTLE.hold(kind):
            done = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=settings.fetch.cli_timeout_sec,
                check=False,
            )
    except subprocess.TimeoutExpired:
        raise SourceError(f"{what}: `{' '.join(argv)}` timed out", transient=True) from None
    if done.returncode != 0:
        raise _cli_failure(what, argv, f"{done.stderr}\n{done.stdout}", done.returncode)
    if not done.stdout.strip():
        raise SourceError(f"{what}: `{' '.join(argv)}` returned no text")
    return done.stdout


def _http_get(url: str) -> tuple[bytes, str]:
    """GET one URL; return (body, content-type)."""
    headers = {"User-Agent": settings.fetch.user_agent, "Accept": "*/*"}
    request = urllib.request.Request(url, headers=headers)
    for delay in (*settings.fetch.http_retry_delays_sec, None):
        try:
            timeout = settings.fetch.http_timeout_sec
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(settings.fetch.max_bytes)
                _check_complete(body, response.headers.get("Content-Length"))
                return body, str(response.headers.get("Content-Type", ""))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if delay is None or not _http_retryable(exc):
                raise SourceError(f"fetch {url}: {exc}", transient=_http_transient(exc)) from None
            time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


class TruncatedDownload(ConnectionError):
    """The connection closed before Content-Length bytes arrived."""


def _check_complete(body: bytes, content_length: str | None) -> None:
    """Raise TruncatedDownload when fewer bytes arrived than the server announced."""
    try:
        expected = int(content_length or "")
    except ValueError:
        return
    if len(body) < min(expected, settings.fetch.max_bytes):
        raise TruncatedDownload(f"truncated download: {len(body)} of {expected} bytes")


def _http_retryable(exc: BaseException) -> bool:
    """True when the same GET is worth repeating in a few seconds."""
    if isinstance(exc, urllib.error.HTTPError) and exc.code == _HTTP_NOT_ACCEPTABLE:
        return True
    return _http_transient(exc)


def _http_transient(exc: BaseException) -> bool:
    """True when a failed GET says nothing about the URL, only about now."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == _HTTP_TOO_MANY_REQUESTS or exc.code >= _HTTP_SERVER_ERROR
    # A refused connection, a DNS hiccup or a timeout is about the network.
    return isinstance(exc, urllib.error.URLError | TimeoutError | ConnectionError)


def _fetch_youtube(url: str) -> Source:
    """Transcript through the `yt` CLI; title through YouTube's oEmbed endpoint."""
    text = _run(
        ["yt", "transcript", url, "--format", "txt"],
        what="youtube transcript",
        kind=SourceKind.youtube,
    )
    return Source(url=url, kind=SourceKind.youtube, title=_youtube_title(url), text=text, tool="yt")


def _youtube_title(url: str) -> str:
    """Video title from oEmbed; the URL itself when that lookup fails."""
    query = urllib.parse.urlencode({"url": url, "format": "json"})
    try:
        body, _ = _http_get(f"https://www.youtube.com/oembed?{query}")
        return str(json.loads(body).get("title") or url)
    except (SourceError, ValueError):
        return url


def _fetch_x(url: str) -> Source:
    """Tweet or thread as markdown through the `x` CLI (costs paid credits)."""
    text = _run(
        ["x", "tweet", url, "--thread", "--format", "md"], what="x thread", kind=SourceKind.x
    )
    first = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), url)
    return Source(url=url, kind=SourceKind.x, title=_title(first), text=text, tool="x")


def _pdf_url(url: str) -> str:
    """arXiv abs/html links point at the PDF; other URLs are used as given."""
    match = _ARXIV_ID_RE.search(url)
    if match is not None:
        return f"https://arxiv.org/pdf/{match.group(1)}"
    return url


def _fetch_pdf(url: str, work_dir: Path) -> Source:
    """Download the PDF into `work_dir` and extract its text with pdftotext."""
    if shutil.which("pdftotext") is None:
        raise SourceError("pdf: `pdftotext` (poppler) is not installed")
    body, _ = _http_get(_pdf_url(url))
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "source.pdf"
    path.write_bytes(body)
    text = _run(["pdftotext", "-layout", str(path), "-"], what="pdf text")
    title = _arxiv_title(url) or _pdf_title(path, text)
    return Source(url=url, kind=SourceKind.pdf, title=title, text=text, tool="pdftotext")


def _arxiv_title(url: str) -> str:
    """Title from the arXiv API for arXiv links; "" for other URLs or on any failure.

    arXiv PDFs carry no metadata title and their first text line is often the
    licence notice, so the heuristic in `_pdf_title` misnames them.
    """
    match = _ARXIV_ID_RE.search(url)
    if match is None:
        return ""
    query = urllib.parse.urlencode({"id_list": match.group(1)})
    try:
        body, _ = _http_get(f"https://export.arxiv.org/api/query?{query}")
    except SourceError:
        return ""
    found = re.search(r"<entry>.*?<title>(.*?)</title>", body.decode("utf-8", "replace"), re.DOTALL)
    if found is None:
        return ""
    return _title(" ".join(html.unescape(found.group(1)).split()))


def _pdf_title(path: Path, text: str) -> str:
    """PDF metadata title when present, else the first non-empty text line."""
    if shutil.which("pdfinfo") is not None:
        try:
            info = subprocess.run(
                ["pdfinfo", str(path)],
                capture_output=True,
                text=True,
                timeout=settings.fetch.http_timeout_sec,
                check=False,
            ).stdout
        except subprocess.TimeoutExpired:
            info = ""
        for line in info.splitlines():
            if line.startswith("Title:") and line[6:].strip():
                return _title(line[6:].strip())
    first = next((line.strip() for line in text.splitlines() if line.strip()), path.name)
    return _title(first)


def _clone_cause(output: str) -> str:
    """One-line reason a `git clone` failed, from its combined output."""
    if re.search(r"repository not found|not found|404|not exist", output, re.IGNORECASE):
        return "repository not found or private (404)"
    if re.search(
        r"authentication|permission denied|access denied|credentials", output, re.IGNORECASE
    ):
        return "authentication required (private repository?)"
    if re.search(r"could not resolve|network|timed out|connection", output, re.IGNORECASE):
        return "network unreachable; retry later"
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "unknown error"


def _repo_sha(dest: Path) -> str:
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


def _read_text_capped(path: Path, cap: int) -> str:
    """File text up to `cap` characters, with a truncation marker past it."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > cap:
        return text[:cap] + f"\n\n... (truncated, {len(text) - cap} more characters)"
    return text


def _repo_tree(dest: Path) -> str:
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


def _count_lines(path: Path) -> int:
    """Newline count of a text file; 0 when it cannot be read as text."""
    try:
        if path.stat().st_size > settings.fetch.max_bytes:
            return 0
        with path.open(encoding="utf-8", errors="strict") as handle:
            return sum(1 for _ in handle)
    except (OSError, ValueError, UnicodeDecodeError):
        return 0


def _count_tree(root: Path) -> tuple[int, int]:
    """(text files, lines) under `root`, skipping VCS and build output."""
    files = 0
    lines = 0
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in REPO_SKIP_DIRS]
        for name in names:
            files += 1
            if files > settings.repo.tree_files_cap:
                return files, lines
            lines += _count_lines(Path(current) / name)
    return files, lines


def _repo_overview(owner: str, repo: str, dest: Path, sha: str) -> str:
    """Provenance plus README, manifests and tree: the Source text of a clone."""
    sections = [f"# {owner}/{repo}", "", f"Commit: {sha}", ""]
    for readme in _REPO_READMES:
        path = dest / readme
        if path.is_file():
            readme_text = strip_boilerplate(_read_text_capped(path, settings.repo.readme_chars))
            sections += ["## README", "", readme_text, ""]
            break
    for manifest in _REPO_MANIFESTS:
        path = dest / manifest
        if path.is_file():
            manifest_text = _read_text_capped(path, settings.repo.manifest_chars)
            sections += [f"## {manifest}", "", "```", manifest_text, "```", ""]
    sections += ["## Top-level layout", "", _repo_tree(dest)]
    return "\n".join(sections).strip() + "\n"


def _fetch_repo(url: str, work_dir: Path) -> Source:
    """Shallow-clone a GitHub repo into `work_dir/repo`; the overview is the text.

    When the clone itself cannot run (no git, timeout, execution failure) the
    error surfaces as a transient `SourceError` so the caller can retry
    later instead of crashing on a raw subprocess error.
    When the clone runs but the repo is unreachable (private repo, 404, no
    network), fall back to the README-first article fetch so a repo page still
    yields its README instead of nothing.
    """
    parts = _github_repo_parts(url)
    if parts is None:
        raise SourceError(f"fetch {url}: not a GitHub repository root or tree URL")
    owner, repo = parts
    if shutil.which("git") is None:
        return _fetch_article(url)
    work_dir.mkdir(parents=True, exist_ok=True)
    dest = work_dir / "repo"
    if dest.exists():
        shutil.rmtree(dest)
    clone_url = f"https://github.com/{owner}/{repo}.git"
    argv = ["git", "clone", "--depth", "1", clone_url, str(dest)]
    cmd = " ".join(argv)
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=settings.fetch.cli_timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SourceError(f"repo: `{cmd}` timed out", transient=True) from None
    except OSError as exc:
        raise SourceError(f"repo: `{cmd}` could not start: {exc}", transient=True) from None
    if done.returncode != 0:
        return _fetch_article(url)
    sha = _repo_sha(dest)
    return Source(
        url=url,
        kind=SourceKind.repo,
        title=f"{owner}/{repo}",
        text=_repo_overview(owner, repo, dest, sha),
        tool="git-clone",
    )


class _MarkdownExtractor(HTMLParser):
    """Visible page text with headings kept as markdown and block breaks kept."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._parts: list[str] = []
        self._heading: str | None = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "nav", "footer", "header", "aside", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _HEADING_TAGS and self._skip == 0:
            self._heading = _HEADING_TAGS[tag]
            self._parts.append(f"\n\n{self._heading} ")
        elif tag in _BLOCK_TAGS and self._skip == 0:
            self._parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "nav", "footer", "header", "aside", "svg"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _HEADING_TAGS:
            self._heading = None
            self._parts.append("\n\n")
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip == 0 and data.strip():
            self._parts.append(re.sub(r"\s+", " ", data) if self._heading else data)

    def text(self) -> str:
        joined = "".join(self._parts)
        joined = re.sub(r"[ \t]+\n", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return html.unescape(joined).strip()


def _fetch_article(url: str) -> Source:
    """Web page stripped to markdown-ish text; PDFs served without .pdf go to pdftotext."""
    body, content_type = _http_get(url)
    if "application/pdf" in content_type.lower() or body[:5] == b"%PDF-":
        raise SourceError(
            f"fetch {url}: served a PDF without a .pdf path; pass the PDF link directly"
        )
    repo = _github_repo_root(url)
    if repo is not None:
        return _fetch_github_article(url, repo[0], repo[1], body)
    parser = _MarkdownExtractor()
    parser.feed(body.decode("utf-8", errors="replace"))
    text = parser.text()
    if len(text) < settings.fetch.min_text_chars:
        raise SourceError(f"fetch {url}: page yielded only {len(text)} characters of text")
    title = re.sub(r"\s+", " ", parser.title).strip() or url
    return Source(url=url, kind=SourceKind.article, title=_title(title), text=text, tool="urllib")


def _github_repo_root(url: str) -> tuple[str, str] | None:
    """(owner, repo) when `url` is a github.com repo landing page, else None."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None
    if parsed.netloc.lower() not in _GITHUB_HOSTS:
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != _REPO_ROOT_SEGMENTS:
        return None
    return segments[0], segments[1]


def _fetch_github_article(url: str, owner: str, repo: str, body: bytes) -> Source:
    """A repo landing page as its README, never as the surrounding page chrome."""
    raw = _github_raw_readme(owner, repo)
    if raw is not None:
        return Source(
            url=url,
            kind=SourceKind.article,
            title=_readme_title(raw, owner, repo),
            text=raw,
            tool="raw-github",
        )
    scoped = _github_readme_text(body)
    if len(scoped) >= settings.fetch.min_text_chars and not _GITHUB_CHROME_HEADING_RE.search(
        scoped
    ):
        return Source(
            url=url,
            kind=SourceKind.article,
            title=_readme_title(scoped, owner, repo),
            text=scoped,
            tool="urllib",
        )
    description = _html_meta_description(body.decode("utf-8", errors="replace"))
    text = f"# {owner}/{repo}\n"
    if description:
        text += f"\n{description}\n"
    text += f"\nRepository: {url}\nNo README found for this repository."
    return Source(
        url=url,
        kind=SourceKind.article,
        title=f"{owner}/{repo}",
        text=text,
        tool="urllib",
    )


def _github_raw_readme(owner: str, repo: str) -> str | None:
    """README.md off raw.githubusercontent.com; None when no ref has one."""
    for ref in _GITHUB_README_REFS:
        try:
            body, _ = _http_get(f"https://{_GITHUB_RAW_HOST}/{owner}/{repo}/{ref}/README.md")
        except SourceError as exc:
            if exc.transient:
                raise
            continue
        text = body.decode("utf-8", errors="replace").strip()
        if text:
            return text
    return None


def _readme_title(text: str, owner: str, repo: str) -> str:
    """First substantive README heading, else `owner/repo`.

    Boilerplate headings (Sponsor, License, ...) are skipped so chunks never
    take a chrome name; falls back to `owner/repo` when nothing else remains.
    """
    for match in re.finditer(r"^#{1,3} +(.+?)\s*$", text, re.MULTILINE):
        title = match.group(1).strip("# ").strip()
        if title and not is_boilerplate_heading(title):
            return _title(title)
    return f"{owner}/{repo}"


def _github_readme_text(body: bytes) -> str:
    """Markdown of the landing page's `#readme` (else first `article`) subtree."""
    probe = _SubtreeExtractor()
    probe.feed(body.decode("utf-8", errors="replace"))
    subtree = probe.subtree()
    if subtree is None:
        return ""
    parser = _MarkdownExtractor()
    parser.feed(subtree)
    lines = [
        line for line in parser.text().splitlines() if not _GITHUB_NOISE_RE.search(line.strip())
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _html_meta_description(page: str) -> str:
    """The page's meta description (usually the repo tagline), else empty."""
    for match in re.finditer(r"<meta\s[^>]*>", page, re.IGNORECASE):
        attrs = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', match.group(0)))
        name = f"{attrs.get('name', '')} {attrs.get('property', '')}".lower()
        if "description" in name and attrs.get("content", "").strip():
            return html.unescape(attrs["content"].strip())
    return ""


class _SubtreeExtractor(HTMLParser):
    """Raw inner HTML of the `#readme` element, else the first `article` element."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.title = ""
        self._in_title = False
        self._capture: list[str] | None = None
        self._capture_tag = ""
        self._capture_readme = False
        self._depth = 0
        self.readme: list[str] | None = None
        self.article: list[str] | None = None

    def subtree(self) -> str | None:
        """The preferred captured subtree, including a truncated trailing one."""
        if self.readme is not None:
            return "".join(self.readme)
        if self.article is not None:
            return "".join(self.article)
        if self._capture is not None:
            return "".join(self._capture)
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title" and self._capture is None:
            self._in_title = True
            return
        if self._capture is not None:
            self._capture.append(self.get_starttag_text() or "")
            if tag == self._capture_tag:
                self._depth += 1
            return
        if dict(attrs).get("id") == "readme":
            self._start_capture(tag, is_readme=True)
        elif tag == "article" and self.article is None and self.readme is None:
            self._start_capture(tag, is_readme=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture is not None:
            self._capture.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            return
        if self._capture is None:
            return
        self._capture.append(f"</{tag}>")
        if tag == self._capture_tag:
            self._depth -= 1
            if self._depth <= 0:
                self._finish_capture()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._capture is not None:
            self._capture.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._capture is not None:
            self._capture.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._capture is not None:
            self._capture.append(f"&#{name};")

    def _start_capture(self, tag: str, *, is_readme: bool) -> None:
        """Begin recording an element's inner HTML, nested depth included."""
        self._capture = [self.get_starttag_text() or ""]
        self._capture_tag = tag
        self._capture_readme = is_readme
        self._depth = 1

    def _finish_capture(self) -> None:
        """File the finished subtree as the readme or the article fallback."""
        if self._capture_readme:
            self.readme = self._capture
        else:
            self.article = self._capture
        self._capture = None
        self._capture_tag = ""
        self._depth = 0
