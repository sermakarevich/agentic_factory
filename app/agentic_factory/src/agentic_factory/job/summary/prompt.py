import json

from agentic_factory.job.summary.contract import SUMMARY_KEY

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


def wrap_prompt(prompt: str) -> str:
    """The prompt the coder gets: the job's own, then the request for the summary."""
    return f"{prompt}\n\n{INSTRUCTION}"
