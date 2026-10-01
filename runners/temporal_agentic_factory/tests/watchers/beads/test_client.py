import json
from pathlib import Path

import pytest

from temporal_agentic_factory.watchers.beads.client import INIT, BeadsClient, NotInitialised
from temporal_agentic_factory.watchers.beads.markers import marker, marker_for
from temporal_agentic_factory.watchers.beads.models import BeadOptions
from temporal_agentic_factory.watchers.beads.shell import BeadsError
from tests.fake_bd import FakeBd, initialised_home


def test_ready_asks_bd_in_the_home_by_priority(tmp_path: Path) -> None:
    home = initialised_home(tmp_path)
    bd = FakeBd({"ready": []})
    BeadsClient(home, 7, bd).ready(limit=3)
    assert bd.calls == [(["ready", "--sort", "priority", "-n", "3", "--json"], home, 7)]


def test_ready_reads_af_job_from_metadata_and_skips_bad_rows(tmp_path: Path) -> None:
    rows = [
        {
            "id": "af-1",
            "title": "T",
            "description": "D",
            "status": "open",
            "metadata": {"af_job": {"provider": "opencode", "workdir": "/tmp"}, "other": 1},
        },
        {"id": "af-2", "metadata": json.dumps({"af_job": {"provider": "claude"}})},
        {"id": "af-3"},
        {"no_id": True},
        "junk",
    ]
    beads = BeadsClient(initialised_home(tmp_path), 1, FakeBd({"ready": rows})).ready(10)
    assert [bead.id for bead in beads] == ["af-1", "af-2", "af-3"]
    assert beads[0].job_fields == {"provider": "opencode", "workdir": "/tmp"}
    assert beads[0].status == "open"
    assert beads[1].job_fields == {"provider": "claude"}
    assert beads[2].job_fields is None


def test_ready_unwraps_the_data_envelope(tmp_path: Path) -> None:
    bd = FakeBd({"ready": {"data": [{"id": "af-1"}]}})
    assert [bead.id for bead in BeadsClient(initialised_home(tmp_path), 1, bd).ready(1)] == ["af-1"]


def test_mutations_are_plain_bd_calls(tmp_path: Path) -> None:
    home = initialised_home(tmp_path)
    bd = FakeBd()
    client = BeadsClient(home, 1, bd)
    client.claim("af-1")
    client.comment("af-1", "hi")
    client.close("af-1")
    client.reopen("af-1")
    client.block("af-1")
    client.unblock("af-1")
    assert [args for args, cwd, _ in bd.calls] == [
        ["update", "af-1", "--claim"],
        ["comment", "af-1", "hi"],
        ["close", "af-1"],
        ["reopen", "af-1"],
        ["update", "af-1", "--status", "blocked"],
        ["update", "af-1", "--status", "open"],
    ]
    assert {cwd for _, cwd, _ in bd.calls} == {home}


def test_in_progress_reads_each_beads_comments(tmp_path: Path) -> None:
    bd = FakeBd(
        {
            "list": [{"id": "af-1", "updated_at": "2026-10-01T10:00:00Z"}],
            "comments": [{"id": "c1", "text": marker("bead-af-1")}],
        }
    )
    states = BeadsClient(initialised_home(tmp_path), 1, bd).in_progress(limit=5)
    assert bd.calls[0][0] == ["list", "--status", "in_progress", "--limit", "5", "--json"]
    assert bd.calls[1][0] == ["comments", "af-1", "--json"]
    assert states[0].updated_at == "2026-10-01T10:00:00Z"
    assert marker_for(states[0].comments) == "bead-af-1"


def test_create_writes_af_job_and_returns_the_id(tmp_path: Path) -> None:
    bd = FakeBd({"create": "af-9\n"})
    client = BeadsClient(initialised_home(tmp_path), 1, bd)
    fields = {"provider": "opencode", "workdir": "/repo"}
    assert client.create("Fix it", "details", 1, fields, BeadOptions()) == "af-9"
    args = bd.calls[0][0]
    assert args[:5] == ["create", "--title", "Fix it", "--description", "details"]
    assert args[args.index("--priority") + 1] == "1"
    assert json.loads(args[args.index("--metadata") + 1]) == {"af_job": fields}
    assert "--deps" not in args
    assert "--parent" not in args
    assert args[-1] == "--silent"


def test_create_passes_chain_options_in_the_same_call(tmp_path: Path) -> None:
    bd = FakeBd({"create": "af-9"})
    options = BeadOptions(
        after=["af-1", "af-2"], parent="af-0", labels=["x", "y"], type="bug", id="af-9"
    )
    BeadsClient(initialised_home(tmp_path), 1, bd).create("T", "", 2, {}, options)
    args = bd.calls[0][0]
    assert args[args.index("--deps") + 1] == "af-1,af-2"
    assert args[args.index("--parent") + 1] == "af-0"
    assert args[args.index("--labels") + 1] == "x,y"
    assert args[args.index("--type") + 1] == "bug"
    assert args[args.index("--id") + 1] == "af-9"
    assert len(bd.calls) == 1


def test_set_job_fields_writes_af_job_only(tmp_path: Path) -> None:
    bd = FakeBd()
    BeadsClient(initialised_home(tmp_path), 1, bd).set_job_fields("af-1", {"model": "m"})
    metadata = json.dumps({"af_job": {"model": "m"}})
    assert bd.calls[0][0] == ["update", "af-1", "--metadata", metadata]


def test_bead_reads_one_shown_bead(tmp_path: Path) -> None:
    rows = [{"id": "af-1", "status": "blocked", "metadata": {"af_job": {"model": "m"}}}]
    bead = BeadsClient(initialised_home(tmp_path), 1, FakeBd({"show": rows})).bead("af-1")
    assert (bead.status, bead.job_fields) == ("blocked", {"model": "m"})


def test_bead_that_is_not_there_raises(tmp_path: Path) -> None:
    with pytest.raises(BeadsError, match="no bead af-1"):
        BeadsClient(initialised_home(tmp_path), 1, FakeBd({"show": []})).bead("af-1")


def test_every_call_refuses_a_home_without_a_database(tmp_path: Path) -> None:
    bd = FakeBd()
    client = BeadsClient(tmp_path / "missing", 1, bd)
    with pytest.raises(NotInitialised, match="af beads init"):
        client.ready(1)
    with pytest.raises(NotInitialised):
        client.claim("af-1")
    assert bd.calls == []


def test_init_makes_the_home_and_runs_bd_init_there(tmp_path: Path) -> None:
    home = tmp_path / "a" / "beads"
    bd = FakeBd()
    assert BeadsClient(home, 1, bd).init() is True
    assert home.is_dir()
    assert bd.calls == [(INIT, home, 1)]
    assert INIT[INIT.index("--prefix") + 1] == "af"


def test_init_is_idempotent(tmp_path: Path) -> None:
    bd = FakeBd()
    assert BeadsClient(initialised_home(tmp_path), 1, bd).init() is False
    assert bd.calls == []


def test_comment_failures_never_fail(tmp_path: Path) -> None:
    BeadsClient(initialised_home(tmp_path), 1, FakeBd(failing={"comment"})).comment("af-1", "hi")


def test_note_failures_raise(tmp_path: Path) -> None:
    with pytest.raises(BeadsError):
        BeadsClient(initialised_home(tmp_path), 1, FakeBd(failing={"comment"})).note("af-1", "hi")
