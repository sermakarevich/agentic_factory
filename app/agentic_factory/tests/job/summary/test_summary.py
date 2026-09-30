import json

from agentic_factory.job.summary.block import find_summary_block
from agentic_factory.job.summary.contract import SUMMARY_KEY, JobSummary
from agentic_factory.job.summary.parse import parse_summary
from agentic_factory.job.summary.prompt import INSTRUCTION, wrap_prompt

GOOD = {
    "task": "say hello",
    "plan": ["run echo"],
    "execution": ["ran echo hello"],
    "result": "hello printed",
    "success": True,
}
BARE = json.dumps({SUMMARY_KEY: GOOD})


def block(summary: dict[str, object]) -> str:
    return f"```json\n{json.dumps({SUMMARY_KEY: summary})}\n```"


def test_wrapped_prompt_keeps_the_job_first_and_asks_for_the_block() -> None:
    wrapped = wrap_prompt("do x")
    assert wrapped.startswith("do x\n\n") and wrapped.endswith(INSTRUCTION)
    assert '"success": <true or false>' in wrapped  # unquoted: a bool is wanted
    assert find_summary_block(wrapped)  # the template itself is detected
    assert parse_summary(find_summary_block(wrapped)) is None  # but never parses as a summary


def test_last_block_in_the_message_wins_and_parses() -> None:
    first = block({**GOOD, "success": False})
    text = f"first try:\n{first}\nactually done:\n{block(GOOD)}\nbye"
    summary = parse_summary(find_summary_block(text))
    assert summary is not None and summary.success and summary.plan == ["run echo"]
    assert find_summary_block('no block here ```json {"other": 1} ```') == ""


def test_detection_ignores_the_fences() -> None:
    assert find_summary_block(f"done.\n{BARE}") == BARE  # no fences at all
    assert find_summary_block(f"done.\n```json\n{BARE}") == BARE  # closing fence never came
    assert find_summary_block(f"{block(GOOD)[:-4]}\nthat is all.") == BARE + "\nthat is all."
    assert find_summary_block(f"{SUMMARY_KEY}: {json.dumps(GOOD)}").startswith(SUMMARY_KEY)


def test_parsers_from_strict_to_lenient() -> None:
    assert parse_summary(BARE) == JobSummary(**GOOD)  # strict
    assert parse_summary(json.dumps(GOOD)) == JobSummary(**GOOD)  # the summary without its key
    assert parse_summary(BARE + "\nthat is all.") == JobSummary(**GOOD)  # prose after it
    sloppy = (
        f'{SUMMARY_KEY}: {{"task": "say hello", "plan": ["run echo",], '
        '"execution": ["ran echo hello"], "result": "hello printed", "success": True,}}'
    )
    assert parse_summary(sloppy) == JobSummary(**GOOD)  # bare key, trailing commas, Python bool
    nested = f'{{"{SUMMARY_KEY}": {{"task": "a }} b", "plan": [], "execution": [], '
    nested += '"result": "r", "success": false}} trailing }'
    got = parse_summary(nested)
    assert got is not None and got.task == "a } b"  # braces inside strings do not close it


def test_broken_block_gives_no_summary_but_keeps_the_text() -> None:
    cut = block(GOOD)[:-8]  # cut mid-object: not json, kept for the repair layer
    found = find_summary_block(cut)
    assert found.startswith('{"job_summary"') and parse_summary(found) is None
    wrong = block({"task": "x", "success": "yes"})  # fields missing, wrong type
    assert find_summary_block(wrong) and parse_summary(find_summary_block(wrong)) is None
