"""The tick activity: one reconcile-and-spawn pass over the beads database."""

from datetime import UTC, datetime

from temporalio import activity

from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.client import BeadsClient
from temporal_agentic_factory.watchers.beads.home import configured_home
from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.poll import poll_once
from temporal_agentic_factory.watchers.beads.shell import run_bd
from temporal_agentic_factory.watchers.beads.temporal import TemporalWorkflows


class BeadsPollActivity:
    @activity.defn
    async def poll(self) -> PollSummary:
        """The tick's I/O: `bd` subprocesses and workflow starts, all here."""
        cfg = settings.beads_poller
        return await poll_once(
            BeadsClient(configured_home(), settings.beads.command_timeout_sec, run_bd),
            TemporalWorkflows(),
            providers=list(settings.providers),
            batch_limit=cfg.batch_limit,
            orphan_timeout_sec=cfg.orphan_timeout_sec,
            now=datetime.now(UTC),
        )
