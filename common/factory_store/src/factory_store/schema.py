from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
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
    """How one try of a job ended. `running` until `finish_try` says otherwise."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# Row ids. SQLite autoincrements only INTEGER primary keys; Postgres gets a bigserial.
ROW_ID = BigInteger().with_variant(Integer(), "sqlite")
# Event payloads: jsonb on Postgres (indexable), plain json elsewhere.
PAYLOAD = JSON().with_variant(JSONB(), "postgresql")
STAMP = DateTime(timezone=True)

metadata = MetaData()

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
    Column("outcome", String, nullable=False, default=Outcome.RUNNING),
    Column("failure", Text, nullable=False, default=""),
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
    Column("kind", String, nullable=False),  # agentic_factory.event.EventKind value
    Column("payload", PAYLOAD, nullable=False),  # the whole Event, json-dumped
)

conversation = Table(
    "conversation",
    metadata,
    Column("session_id", String, ForeignKey("session.id"), primary_key=True),
    Column("built_at", STAMP, nullable=False),
    Column("events_count", Integer, nullable=False),
    Column("text", Text, nullable=False),
)

report = Table(
    "report",
    metadata,
    Column("session_id", String, ForeignKey("session.id"), primary_key=True),
    Column("created_at", STAMP, nullable=False),
    Column("result", PAYLOAD, nullable=False),  # the JobResult, json-dumped; {} when the job failed
    Column("summary", PAYLOAD, nullable=False),  # the structured report a model wrote
    Column("verdict", String, nullable=False),
)
