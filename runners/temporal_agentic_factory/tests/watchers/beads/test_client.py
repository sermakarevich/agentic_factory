import json
from pathlib import Path

import pytest

from temporal_agentic_factory.watchers.beads.client import (
    INIT,
    MARKER_PREFIX,
    BeadsClient,
    NotInitialised,
    marker,
    marker_for,
)
from tests.fake_bd import FakeBd, initialised_home


def test_ready_asks_bd_in_the_home_by_priority(tmp_path: Path) -> None:
    home = initialised_home(tmp_path)
    bd = FakeBd({"ready": []})
    BeadsClient(home, 7, bd).ready(limit=3)
    assert bd.calls == [(["ready", "--sort", "priority", "-n", "3", "--json"], home, 7)]


def test_ready_reads_routing_from_metadata_and_skips_bad_rows(tmp_path: Path) -> None:
    rows = [
        {
            "id": "af-1",
            "title": "T",
            "description": "D",
            "metadata": {"af_provider": "opencode", "af_cwd": "/tmp", "af_model": "m"},
        },
        {"id": "af-2", "metadata": json.dumps({"af_provider": "claude"})},
        {"id": "af-3"},
        {"no_id": True},
        "junk",
    ]
    beads = BeadsClient(initialised_home(tmp_path), 1, FakeBd({"ready": rows})).ready(10)
    assert [bead.id for bead in beads] == ["af-1", "af-2", "af-3"]
    assert (beads[0].provider, beads[0].cwd, beads[0].model) == ("opencode", "/tmp", "m")
    assert (beads[1].provider, beads[1].cwd, beads[1].model) == ("claude", "", "")
    assert (beads[2].provider, beads[2].cwd) == ("", "")


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
    assert [args for args, cwd, _ in bd.calls] == [
        ["update", "af-1", "--claim"],
        ["comment", "af-1", "hi"],
        ["close", "af-1"],
        ["reopen", "af-1"],
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


def test_create_writes_routing_metadata_and_returns_the_id(tmp_path: Path) -> None:
    bd = FakeBd({"create": "af-9\n"})
    client = BeadsClient(initialised_home(tmp_path), 1, bd)
    assert client.create("Fix it", "details", 1, "opencode", "/repo", "") == "af-9"
    args = bd.calls[0][0]
    assert args[:5] == ["create", "--title", "Fix it", "--description", "details"]
    assert args[args.index("--priority") + 1] == "1"
    assert json.loads(args[args.index("--metadata") + 1]) == {
        "af_provider": "opencode",
        "af_cwd": "/repo",
    }


def test_create_stores_a_given_model(tmp_path: Path) -> None:
    bd = FakeBd({"create": "af-9"})
    BeadsClient(initialised_home(tmp_path), 1, bd).create("T", "", 2, "claude", "/r", "opus")
    args = bd.calls[0][0]
    assert json.loads(args[args.index("--metadata") + 1])["af_model"] == "opus"


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


def test_marker_round_trip() -> None:
    assert marker_for(["noise", marker("bead-bd-1")]) == "bead-bd-1"
    assert marker_for(["nothing here"]) is None
    assert MARKER_PREFIX in marker("bead-bd-1")


def test_comment_failures_never_fail(tmp_path: Path) -> None:
    BeadsClient(initialised_home(tmp_path), 1, FakeBd(failing={"comment"})).comment("af-1", "hi")
