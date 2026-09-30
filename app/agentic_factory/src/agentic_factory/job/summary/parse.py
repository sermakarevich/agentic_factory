import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from agentic_factory.job.summary.contract import SUMMARY_KEY, JobSummary

_decoder = json.JSONDecoder()


def parse_summary(block: str) -> JobSummary | None:
    """A block into a summary, or None. Each parser is tried in turn,
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


def _lenient(block: str) -> Any:
    """The mistakes seen from models: a bare key, trailing commas, Python
    literals, text after the closing brace."""
    text = _from_first_brace(block)
    text = _balanced(text)
    text = _with_quoted_key(text)
    text = _without_trailing_commas(text)
    text = _with_json_literals(text)
    return json.loads(text)


def _from_first_brace(block: str) -> str:
    """The block from its first brace; a block with no braces gets a pair."""
    return block[block.index("{") :] if "{" in block else "{" + block + "}"


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


BARE_KEY = re.compile(r"(?<![\"\w])" + SUMMARY_KEY + r"(?=\s*:)")


def _with_quoted_key(text: str) -> str:
    return BARE_KEY.sub(f'"{SUMMARY_KEY}"', text)


TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _without_trailing_commas(text: str) -> str:
    return TRAILING_COMMA.sub(r"\1", text)


PYTHON_LITERALS = {"True": "true", "False": "false", "None": "null"}


def _with_json_literals(text: str) -> str:
    for literal, replacement in PYTHON_LITERALS.items():
        text = re.sub(r"\b" + literal + r"\b", replacement, text)
    return text


PARSERS: list[Callable[[str], Any]] = [_strict, _leading_object, _lenient]
