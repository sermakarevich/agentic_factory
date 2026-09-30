from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, RowMapping, Table, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from factory_store import schema
from factory_store.schema import Outcome


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class StoredEvent:
    """One `event` row: the order (`id`) and try it belongs to, plus the event as stored."""

    id: int
    session_id: str
    attempt: int
    at: datetime
    kind: str
    payload: dict[str, Any]


class Store:
    """The factory's database, one engine per process. Every method is one
    short transaction; callers never see a connection."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, url: str) -> "Store":
        return cls(create_async_engine(url))

    async def create_all(self) -> None:
        """Tables from the schema, for tests. Deployments run the migrations."""
        async with self.engine.begin() as conn:
            await conn.run_sync(schema.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def start_session(
        self, session_id: str, provider: str, model: str, workdir: str, prompt: str
    ) -> None:
        """Insert the session; a second call for the same id changes nothing
        (the caller may be retried)."""
        async with self.engine.begin() as conn:
            await _insert_if_absent(
                conn,
                schema.session,
                {"id": session_id},
                {
                    "provider": provider,
                    "model": model,
                    "workdir": workdir,
                    "prompt": prompt,
                    "created_at": _now(),
                },
            )

    async def start_try(self, session_id: str, attempt: int) -> None:
        """Insert the try as running. If a row for (session_id, attempt) already exists,
        set it back to running with a new started_at, ended_at None, failure "" (same
        idempotence reason). An earlier try of the session still marked running died
        with its runner and could never close itself: it is closed as abandoned here."""
        async with self.engine.begin() as conn:
            await _abandon_running_before(conn, session_id, attempt)
            await _upsert(
                conn,
                schema.attempt,
                {"session_id": session_id, "attempt": attempt},
                {
                    "started_at": _now(),
                    "ended_at": None,
                    "outcome": Outcome.RUNNING.value,
                    "failure": "",
                },
            )

    async def append_event(
        self, session_id: str, attempt: int, at: datetime, kind: str, payload: dict[str, Any]
    ) -> int:
        """Insert one event; return its row id (the session-wide order)."""
        async with self.engine.begin() as conn:
            result = await conn.execute(
                insert(schema.event).values(
                    session_id=session_id,
                    attempt=attempt,
                    at=at,
                    kind=kind,
                    payload=payload,
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            return int(pk[0])

    async def load_events(self, session_id: str) -> list[StoredEvent]:
        """Every event of the session, ordered by id ascending."""
        async with self.engine.begin() as conn:
            result = await conn.execute(
                select(schema.event)
                .where(schema.event.c.session_id == session_id)
                .order_by(schema.event.c.id)
            )
            return [_stored_event(row) for row in result.mappings().all()]

    async def finish_try(
        self, session_id: str, attempt: int, outcome: Outcome, failure: str = ""
    ) -> None:
        """Set outcome, failure and ended_at = now (UTC) on the try row."""
        async with self.engine.begin() as conn:
            await conn.execute(
                update(schema.attempt)
                .where(schema.attempt.c.session_id == session_id)
                .where(schema.attempt.c.attempt == attempt)
                .values(outcome=outcome.value, failure=failure, ended_at=_now())
            )

    async def save_conversation(self, session_id: str, text: str, events_count: int) -> None:
        """Insert or replace the conversation row (built_at = now UTC)."""
        async with self.engine.begin() as conn:
            await _upsert(
                conn,
                schema.conversation,
                {"session_id": session_id},
                {"built_at": _now(), "events_count": events_count, "text": text},
            )

    async def save_report(
        self, session_id: str, result: dict[str, Any], summary: dict[str, Any], verdict: str
    ) -> None:
        """Insert or replace the report row (created_at = now UTC)."""
        async with self.engine.begin() as conn:
            await _upsert(
                conn,
                schema.report,
                {"session_id": session_id},
                {"created_at": _now(), "result": result, "summary": summary, "verdict": verdict},
            )


ABANDONED = "abandoned: a later try started while this one was still running"


async def _abandon_running_before(conn: AsyncConnection, session_id: str, attempt: int) -> None:
    """Close every earlier try of the session still marked running: it died with
    its runner and could never close itself."""
    await conn.execute(
        update(schema.attempt)
        .where(schema.attempt.c.session_id == session_id)
        .where(schema.attempt.c.attempt < attempt)
        .where(schema.attempt.c.outcome == Outcome.RUNNING.value)
        .values(ended_at=_now(), outcome=Outcome.FAILED.value, failure=ABANDONED)
    )


Key = dict[str, Any]  # the columns that identify one row, with their values


async def _insert_if_absent(conn: AsyncConnection, table: Table, key: Key, values: Key) -> None:
    if not await _row_exists(conn, table, key):
        await conn.execute(insert(table).values(**key, **values))


async def _upsert(conn: AsyncConnection, table: Table, key: Key, values: Key) -> None:
    """Insert the row identified by `key` with `values`, or set `values` on it
    when it exists. Plain select-then-write: the store has one writer per row."""
    if await _row_exists(conn, table, key):
        await conn.execute(update(table).where(*_matching(table, key)).values(**values))
    else:
        await conn.execute(insert(table).values(**key, **values))


async def _row_exists(conn: AsyncConnection, table: Table, key: Key) -> bool:
    found = await conn.execute(select(table).where(*_matching(table, key)))
    return found.first() is not None


def _matching(table: Table, key: Key) -> list[ColumnElement[bool]]:
    return [table.c[column] == value for column, value in key.items()]


def _stored_event(row: RowMapping) -> StoredEvent:
    return StoredEvent(
        id=row["id"],
        session_id=row["session_id"],
        attempt=row["attempt"],
        at=_as_utc(row["at"]),
        kind=row["kind"],
        payload=row["payload"],
    )


def _as_utc(at: datetime) -> datetime:
    """The stored time with its zone: sqlite drops it, and every write is UTC."""
    return at if at.tzinfo is not None else at.replace(tzinfo=UTC)
