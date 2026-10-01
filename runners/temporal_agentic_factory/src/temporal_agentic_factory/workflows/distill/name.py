"""The short name a distill run shows in the UI: the tail of its url."""

from pathlib import PurePosixPath
from urllib.parse import urlparse


def source_name(url: str) -> str:
    """`arxiv.org/2401.12345` for `https://arxiv.org/abs/2401.12345`: the host
    and the last path segment; a local path gives its file name."""
    parsed = urlparse(url)
    if not parsed.netloc:
        return PurePosixPath(url).name or url
    tail = PurePosixPath(parsed.path).name
    return f"{parsed.netloc}/{tail}" if tail else parsed.netloc
