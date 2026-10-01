import json
import shlex
from string import Template

from agentic_factory.job.submission.contract import Schema

INSTRUCTION = Template(
    """When the work is over, done or not, submit the result of this job: one JSON object \
matching the schema below, given on stdin to this shell command:

$command <<'JSON'
{ ... }
JSON

Its `report` says what you did, each item with its evidence; when the schema has an \
`output`, that is what the job asked you to hand back. The command prints `ok`, or \
`invalid:` and every error with its path. Fix the JSON and run the command again until \
it prints `ok`; the last submission that printed `ok` counts. Then stop.

The JSON Schema:
$schema"""
)


def wrap_prompt(prompt: str, schema: Schema, command: str) -> str:
    """The prompt the workflow gives the job: the job's own, then the request
    to submit its result with `command`, and the full submission schema as
    indented JSON, `$defs` included, so nested shapes are visible."""
    schema_text = json.dumps(schema, indent=2)
    return f"{prompt}\n\n{INSTRUCTION.substitute(command=command, schema=schema_text)}"


def command_prefix(af: str) -> str:
    """`af output submit`, with the given `af` executable: what a coder's tool rule allows."""
    return f"{shlex.quote(af)} output submit"


def submit_command(af: str, session_id: str) -> str:
    """`af output submit <session-id>`: the command the coder submits with."""
    return f"{command_prefix(af)} {shlex.quote(session_id)}"
