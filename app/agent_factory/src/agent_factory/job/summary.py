import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SUMMARY_KEY = "job_summary"


class JobSummary(BaseModel):
    """The coder's own account of the job, asked for by `wrap_prompt`.
    A claim, not a verdict: the workflow checks it against the stats.
    `extra="forbid"` because the repair step sends this schema in strict mode."""

    model_config = ConfigDict(extra="forbid")
    task: str = Field(description="One sentence: what was asked.")
    plan: list[str] = Field(description="What the coder set out to do.")
    execution: list[str] = Field(description="What it actually did.")
    result: str = Field(description="One sentence: the state now.")
    success: bool


TEMPLATE = {
    SUMMARY_KEY: {
        "task": "<one sentence: what was asked>",
        "plan": ["<a step you planned>"],
        "execution": ["<something you did>"],
        "result": "<one sentence: the state now>",
        "success": "<true or false>",
    }
}
# `success` is shown unquoted, so the model writes a bool, not the string "true".
TEMPLATE_TEXT = json.dumps(TEMPLATE, indent=2).replace('"<true or false>"', "<true or false>")
INSTRUCTION = (
    "When you are done, end your final message with this json block, filled in. "
    "Close it with ``` and write nothing after it:\n\n"
    f"```json\n{TEMPLATE_TEXT}\n```"
)

# Layer 3, detection: the key, quoted or not, followed by a colon. A partial
# match on purpose; whether what follows is a summary is the parsers' question.
KEY = re.compile(r"\"?" + SUMMARY_KEY + r"\"?\s*:")
OBJECT_START = re.compile(r"\{\s*" + KEY.pattern)
FENCE = "```"

_decoder = json.JSONDecoder()


def wrap_prompt(prompt: str) -> str:
    """The prompt the coder gets: the job's own, then the request for the summary."""
    return f"{prompt}\n\n{INSTRUCTION}"


def find_summary_block(text: str) -> str:
    """The text of the last summary in a model message, or empty. The coder may
    write it in any message, not only the last one, and coders do drop the
    closing fence: the block runs from the object's opening brace (or the bare
    key) to the next fence or the end of the message. Not parsed here."""
    starts = [m.start() for m in OBJECT_START.finditer(text)] or [
        m.start() for m in KEY.finditer(text)
    ]
    if not starts:
        return ""
    start = starts[-1]
    fence = text.find(FENCE, start)
    return text[start : fence if fence != -1 else len(text)].strip()


def parse_summary(block: str) -> JobSummary | None:
    """Layer 4: a block into a summary, or None. Each parser is tried in turn,
    strictest first; the summary must still match `JobSummary`."""
    for parser in PARSERS:
        try:
            return _validate(parser(block))
        except (ValueError, TypeError, KeyError, ValidationError):
            continue
    return None


def _validate(data: Any) -> JobSummary:
    if isinstance(data, dict) and SUMMARY_KEY in data:
        data = data[SUMMARY_KEY]
    return JobSummary.model_validate(data)


def _strict(block: str) -> Any:
    return json.loads(block)


def _leading_object(block: str) -> Any:
    """Valid json followed by anything: a fence, prose, a second copy."""
    data, _ = _decoder.raw_decode(block, block.index("{"))
    return data


TRAILING_COMMA = re.compile(r",(\s*[}\]])")
PYTHON_LITERALS = {"True": "true", "False": "false", "None": "null"}
BARE_KEY = re.compile(r"(?<![\"\w])" + SUMMARY_KEY + r"(?=\s*:)")


def _lenient(block: str) -> Any:
    """The mistakes seen from models: a bare key, trailing commas, Python
    literals, text after the closing brace."""
    text = block[block.index("{") :] if "{" in block else "{" + block + "}"
    text = _balanced(text)
    text = BARE_KEY.sub(f'"{SUMMARY_KEY}"', text)
    text = TRAILING_COMMA.sub(r"\1", text)
    for literal, replacement in PYTHON_LITERALS.items():
        text = re.sub(r"\b" + literal + r"\b", replacement, text)
    return json.loads(text)


def _balanced(text: str) -> str:
    """`text` from its first brace to the one that closes it, strings respected."""
    depth, in_string, escaped = 0, False, False
    for i, char in enumerate(text):
        if in_string:
            escaped = char == "\\" and not escaped
            in_string = char != '"' or escaped
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[: i + 1]
    return text


PARSERS: list[Callable[[str], Any]] = [_strict, _leading_object, _lenient]
