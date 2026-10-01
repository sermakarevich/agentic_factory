import time
import urllib.error
import urllib.request

from distill.settings.load import settings
from distill.sources.source import SourceError

NOT_ACCEPTABLE = 406
TOO_MANY_REQUESTS = 429
SERVER_ERROR = 500


def get(url: str) -> tuple[bytes, str]:
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
            if delay is None or not _retryable(exc):
                raise SourceError(f"fetch {url}: {exc}", transient=transient(exc)) from None
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


def transient(exc: BaseException) -> bool:
    """True when a failed GET says nothing about the URL, only about now."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == TOO_MANY_REQUESTS or exc.code >= SERVER_ERROR
    return isinstance(exc, urllib.error.URLError | TimeoutError | ConnectionError)


def _retryable(exc: BaseException) -> bool:
    """True when the same GET is worth repeating in a few seconds."""
    if isinstance(exc, urllib.error.HTTPError) and exc.code == NOT_ACCEPTABLE:
        return True
    return transient(exc)
