"""The beads side of af: ready beads, claims, comments, closes, blocks, new beads.

Every call is `bd ...` run in the database's home (`[beads].home`), and every
call but `init` first checks that the home holds a database: `bd` would
otherwise walk up the tree and find another one. Every read tolerates rows
with missing keys: `bd --json` shapes drift.
"""

import contextlib
import json
from pathlib import Path
from typing import Any

from temporal_agentic_factory.watchers.beads.models import Bead, BeadOptions, BeadState, Status
from temporal_agentic_factory.watchers.beads.shell import BeadsError, Run

JOB_KEY = "af_job"  # the bead metadata key holding the job's parameters
DATABASE_FOLDER = ".beads"
PREFIX = "af"
INIT = ["init", "--prefix", PREFIX, "--non-interactive", "--quiet", "--skip-agents", "--skip-hooks"]


class NotInitialised(BeadsError):
    """The home holds no beads database yet."""


class BeadsClient:
    """The calls on one beads database. `run` is injected so tests need no `bd`."""

    def __init__(self, home: Path, timeout_sec: int, run: Run) -> None:
        self.home = home
        self.timeout_sec = timeout_sec
        self._run = run

    def initialised(self) -> bool:
        """Whether the home holds a beads database."""
        return (self.home / DATABASE_FOLDER).is_dir()

    def require_initialised(self) -> None:
        """Raise NotInitialised, naming the fix, when the home holds no database."""
        if not self.initialised():
            raise NotInitialised(f"no beads database at {self.home}; run `af beads init`")

    def init(self) -> bool:
        """Make the home and its database; False when it was there already."""
        if self.initialised():
            return False
        self.home.mkdir(parents=True, exist_ok=True)
        self._run(INIT, self.home, self.timeout_sec)
        return True

    def ready(self, limit: int) -> list[Bead]:
        """Startable beads with their job parameters, highest priority first."""
        rows = self._json(["ready", "--sort", "priority", "-n", str(limit)])
        return [_bead_of(row) for row in _rows_with_id(rows)]

    def in_progress(self, limit: int) -> list[BeadState]:
        """Beads currently worked on, each with its comments for marker scans."""
        rows = self._json(["list", "--status", Status.IN_PROGRESS, "--limit", str(limit)])
        return [
            BeadState(
                id=str(row["id"]),
                updated_at=str(row.get("updated_at") or row.get("updated") or ""),
                comments=self.comments(str(row["id"])),
            )
            for row in _rows_with_id(rows)
        ]

    def comments(self, bead_id: str) -> list[str]:
        """Comment bodies on one bead, newest last; [] when unreadable."""
        try:
            rows = self._json(["comments", bead_id])
        except BeadsError:
            return []
        bodies = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, str):
                bodies.append(row)
            elif isinstance(row, dict):
                for key in ("body", "text", "comment"):
                    if row.get(key):
                        bodies.append(str(row[key]))
                        break
        return bodies

    def bead(self, bead_id: str) -> Bead:
        """One bead as `bd show` reads it; raises BeadsError when there is none."""
        rows = _rows_with_id(_listed(self._json(["show", bead_id])))
        if not rows:
            raise BeadsError(f"no bead {bead_id}")
        return _bead_of(rows[0])

    def create(
        self,
        title: str,
        description: str,
        priority: int,
        job_fields: dict[str, Any],
        options: BeadOptions,
    ) -> str:
        """A new open bead with its job parameters as `af_job` metadata; its id."""
        args = ["create", "--title", title, "--description", description]
        args += ["--priority", str(priority), *_option_args(options)]
        args += ["--metadata", json.dumps({JOB_KEY: job_fields}), "--silent"]
        return self._bd(args).strip()

    def set_job_fields(self, bead_id: str, job_fields: dict[str, Any]) -> None:
        """The bead's `af_job` replaced; bd merges metadata by key, so others stay."""
        self._bd(["update", bead_id, "--metadata", json.dumps({JOB_KEY: job_fields})])

    def claim(self, bead_id: str) -> None:
        """Take one bead to in_progress; raises BeadsError when it is already taken."""
        self._bd(["update", bead_id, "--claim"])

    def comment(self, bead_id: str, text: str) -> None:
        """A best-effort note; a failed comment never fails the tick."""
        with contextlib.suppress(BeadsError):
            self._bd(["comment", bead_id, text])

    def note(self, bead_id: str, text: str) -> None:
        """A comment that must land before the next step; raises BeadsError when it fails."""
        self._bd(["comment", bead_id, text])

    def close(self, bead_id: str) -> None:
        """Close a finished bead; raises BeadsError when it fails."""
        self._bd(["close", bead_id])

    def reopen(self, bead_id: str) -> None:
        """Release an orphaned claim back to open; raises BeadsError when it fails."""
        self._bd(["reopen", bead_id])

    def block(self, bead_id: str) -> None:
        """Mark a bead blocked, so it and its dependents stay unready; raises BeadsError."""
        self._bd(["update", bead_id, "--status", Status.BLOCKED])

    def unblock(self, bead_id: str) -> None:
        """A blocked bead back to open, ready again; raises BeadsError when it fails."""
        self._bd(["update", bead_id, "--status", Status.OPEN])

    def output(self, args: list[str]) -> str:
        """`bd <args>` stdout as is, for the cli to print."""
        return self._bd(args)

    def _bd(self, args: list[str]) -> str:
        """`bd <args>` in the home, once the home holds a database."""
        self.require_initialised()
        return self._run(args, self.home, self.timeout_sec)

    def _json(self, args: list[str]) -> Any:
        """`bd <args> --json` parsed."""
        return _parsed(self._bd([*args, "--json"]))


def _parsed(raw: str) -> Any:
    """JSON output without the optional `{"data": ...}` envelope; [] when empty."""
    if not raw.strip():
        return []
    parsed: Any = json.loads(raw)
    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return parsed


def _listed(rows: Any) -> list[Any]:
    """`bd show` answers a list of one, or the row itself."""
    return rows if isinstance(rows, list) else [rows]


def _rows_with_id(rows: Any) -> list[dict[str, Any]]:
    """The rows that are objects with an id; anything else is dropped."""
    listed = rows if isinstance(rows, list) else []
    return [row for row in listed if isinstance(row, dict) and row.get("id")]


def _option_args(options: BeadOptions) -> list[str]:
    """The `bd create` flags for the options that are set."""
    args = ["--deps", ",".join(options.after)] if options.after else []
    args += ["--parent", options.parent] if options.parent else []
    args += ["--labels", ",".join(options.labels)] if options.labels else []
    args += ["--type", options.type] if options.type else []
    args += ["--id", options.id] if options.id else []
    return args


def _bead_of(row: dict[str, Any]) -> Bead:
    """One `bd ready`/`bd show` row as a Bead, its job parameters as stored."""
    return Bead(
        id=str(row["id"]),
        title=str(row.get("title") or ""),
        description=str(row.get("description") or ""),
        status=str(row.get("status") or ""),
        job_fields=_json_or_as_is(_metadata_of(row).get(JOB_KEY)),
    )


def _metadata_of(row: dict[str, Any]) -> dict[str, Any]:
    """A row's metadata as a dict: an object, a JSON string of one, or {}."""
    metadata = _json_or_as_is(row.get("metadata"))
    return metadata if isinstance(metadata, dict) else {}


def _json_or_as_is(value: Any) -> Any:
    """A JSON string parsed; anything else, or a string that is not JSON, as is."""
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            return json.loads(value)
    return value
