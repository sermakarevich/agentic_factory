import re

from agentic_factory.job.summary.contract import SUMMARY_KEY

# Detection: the key, quoted or not, followed by a colon. A partial match on
# purpose; whether what follows is a summary is `summary_parse`'s question.
KEY = re.compile(r"\"?" + SUMMARY_KEY + r"\"?\s*:")
OBJECT_START = re.compile(r"\{\s*" + KEY.pattern)
FENCE = "```"


def find_summary_block(text: str) -> str:
    """The text of the last summary in a model message, or empty. The coder may
    write it in any message, not only the last one, and coders do drop the
    closing fence: the block runs from the object's opening brace (or the bare
    key) to the next fence or the end of the message. Not parsed here."""
    start = _last_block_start(text)
    if start is None:
        return ""
    return text[start : _block_end(text, start)].strip()


def _last_block_start(text: str) -> int | None:
    """Where the last `{"job_summary":` begins, else the last bare key, else None."""
    starts = [m.start() for m in OBJECT_START.finditer(text)] or [
        m.start() for m in KEY.finditer(text)
    ]
    return starts[-1] if starts else None


def _block_end(text: str, start: int) -> int:
    """The next fence after `start`, or the end of the message when none came."""
    fence = text.find(FENCE, start)
    return fence if fence != -1 else len(text)
