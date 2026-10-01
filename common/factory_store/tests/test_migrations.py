import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).parent.parent  # where alembic.ini is


def migrate(database: Path, revision: str) -> None:
    """`alembic upgrade <revision>` on a sqlite file, in a process of its own:
    the shared settings read the store url once, at import."""
    url = f"sqlite+aiosqlite:///{database}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=PACKAGE,
        env={**os.environ, "AF_STORE__URL": url},
        check=True,
        capture_output=True,
    )


def tables(database: Path) -> set[str]:
    with sqlite3.connect(database) as conn:
        rows = conn.execute("select name from sqlite_master where type = 'table'").fetchall()
    return {row[0] for row in rows}


def columns(database: Path, table: str) -> set[str]:
    with sqlite3.connect(database) as conn:
        rows = conn.execute(f"pragma table_info({table})").fetchall()
    return {row[1] for row in rows}


def test_every_migration_applies_on_an_empty_database(tmp_path: Path) -> None:
    database = tmp_path / "store.db"
    migrate(database, "head")
    assert {"session", "structured_output", "output_schema", "report"} <= tables(database)
    assert columns(database, "report") == {"session_id", "created_at", "report", "verdict"}


def test_the_output_schema_migration_applies_on_an_existing_database(tmp_path: Path) -> None:
    database = tmp_path / "store.db"
    migrate(database, "9410ff787989")
    with sqlite3.connect(database) as conn:
        conn.execute(
            "insert into session (id, provider, model, workdir, prompt, created_at) "
            "values ('s1', 'claude', 'm', '/w', 'do it', '2026-10-01 12:00:00')"
        )
    assert "output_schema" not in tables(database)
    migrate(database, "head")
    assert "output_schema" in tables(database)
    with sqlite3.connect(database) as conn:
        assert conn.execute("select id from session").fetchall() == [("s1",)]


def test_the_report_migration_keeps_an_existing_report(tmp_path: Path) -> None:
    database = tmp_path / "store.db"
    migrate(database, "cc6c4eebce08")
    with sqlite3.connect(database) as conn:
        conn.execute(
            "insert into session (id, provider, model, workdir, prompt, created_at) "
            "values ('s1', 'claude', 'm', '/w', 'do it', '2026-10-01 12:00:00')"
        )
        conn.execute(
            "insert into report (session_id, created_at, result, summary, verdict) "
            "values ('s1', '2026-10-01 12:00:00', '{}', '{\"task\": \"t\"}', 'done')"
        )
    migrate(database, "head")
    assert columns(database, "report") == {"session_id", "created_at", "report", "verdict"}
    with sqlite3.connect(database) as conn:
        row = conn.execute("select session_id, report, verdict from report").fetchone()
    assert row == ("s1", '{"task": "t"}', "done")
