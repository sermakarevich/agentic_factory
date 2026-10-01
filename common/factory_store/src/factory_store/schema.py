from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB


class Outcome(StrEnum):
    """How one try, or the whole job, ended. A try is `running` until
    `finish_try` says otherwise."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# Row ids. SQLite autoincrements only INTEGER primary keys; Postgres gets a bigserial.
ROW_ID = BigInteger().with_variant(Integer(), "sqlite")
# Event payloads: jsonb on Postgres (indexable), plain json elsewhere.
PAYLOAD = JSON().with_variant(JSONB(), "postgresql")
STAMP = DateTime(timezone=True)

metadata = MetaData()


def totals_columns() -> list[Column[Any]]:
    """What a try, and a job over its tries, added up to. The same columns on
    both tables, flat so that sql can sum them; `Totals` mirrors them."""
    return [
        Column("input_tokens", BigInteger, nullable=False, default=0),
        Column("output_tokens", BigInteger, nullable=False, default=0),
        Column("cache_read_tokens", BigInteger, nullable=False, default=0),
        Column("cache_write_tokens", BigInteger, nullable=False, default=0),
        Column("cost_usd", Float, nullable=False, default=0.0),
        Column("duration_sec", Float, nullable=False, default=0.0),
        Column("turns", Integer, nullable=False, default=0),
        Column("tool_calls", Integer, nullable=False, default=0),
        Column("tool_failures", Integer, nullable=False, default=0),
    ]


session = Table(
    "session",
    metadata,
    Column("id", String, primary_key=True),  # the coder's session id; the job's key
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False, default=""),
    Column("workdir", String, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("created_at", STAMP, nullable=False),
)

attempt = Table(
    "attempt",
    metadata,
    Column("id", ROW_ID, primary_key=True, autoincrement=True),
    Column("session_id", String, ForeignKey("session.id"), nullable=False),
    Column("attempt", Integer, nullable=False),  # Temporal's attempt number, from 1
    Column("started_at", STAMP, nullable=False),
    Column("ended_at", STAMP, nullable=True),
    Column("outcome", String, nullable=False, default=Outcome.RUNNING.value),
    Column("failure", Text, nullable=False, default=""),
    *totals_columns(),
    Column("result", PAYLOAD, nullable=False, default=dict),  # the JobResult as json; {} on failure
    UniqueConstraint("session_id", "attempt", name="uq_attempt_session_attempt"),
)

# One row per event, in insert order: `id` is the order of the whole session
# across tries and runner restarts; `at` is the coder's own timestamp.
event = Table(
    "event",
    metadata,
    Column("id", ROW_ID, primary_key=True, autoincrement=True),
    Column("session_id", String, ForeignKey("session.id"), nullable=False, index=True),
    Column("attempt", Integer, nullable=False),
    Column("at", STAMP, nullable=False),
    Column("kind", String, nullable=False),  # the event kind, as the app names it
    Column("payload", PAYLOAD, nullable=False),  # the whole Event, json-dumped
)

# One row per job: the workflow run over every try of the session, written
# once at its end, summed over the tries so a cost query needs no join.
job = Table(
    "job",
    metadata,
    Column("session_id", String, ForeignKey("session.id"), primary_key=True),
    Column("started_at", STAMP, nullable=False),  # the first try's start
    Column("ended_at", STAMP, nullable=False),  # when the row was written, at the job's end
    Column("tries", Integer, nullable=False),
    Column("outcome", String, nullable=False),  # done | failed
    Column("failure", Text, nullable=False, default=""),  # the last try's, when failed
    *totals_columns(),
    Column("result", PAYLOAD, nullable=False, default=dict),  # the last try's result; {} on failure
    Column("verdict", String, nullable=False, default=""),  # the report's; unknown without one
)

# The report the coder submitted with `af output submit` at the end of its
# job; a resubmit replaces it. Jobs whose coder submitted nothing have none.
report = Table(
    "report",
    metadata,
    Column("session_id", String, ForeignKey("session.id"), primary_key=True),
    Column("created_at", STAMP, nullable=False),
    Column("report", PAYLOAD, nullable=False),  # the report the coder submitted
    Column("verdict", String, nullable=False),  # done | partial | failed, as in the report
)

# The JSON schema a job's submission must match (its report and, when asked
# for, its output), saved before the coder starts so that `af output submit`
# can check against it.
output_schema = Table(
    "output_schema",
    metadata,
    Column("session_id", String, ForeignKey("session.id"), primary_key=True),
    Column("created_at", STAMP, nullable=False),
    Column("schema", PAYLOAD, nullable=False),  # the submission schema the workflow built
)

# The structured output a workflow asked the job for, submitted by the coder.
# Only jobs asked for one have a row.
structured_output = Table(
    "structured_output",
    metadata,
    Column("session_id", String, ForeignKey("session.id"), primary_key=True),
    Column("created_at", STAMP, nullable=False),
    Column("source", String, nullable=False),  # submitted; older rows: last_message | conversation
    Column("schema", PAYLOAD, nullable=False),  # the JSON schema the submission was checked against
    Column("structured_output", PAYLOAD, nullable=False),  # the output, matching it
)
