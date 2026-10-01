"""The beads poll workflow: one tick that claims ready beads and spawns their jobs.

A Temporal Schedule fires this every `beads_poller.interval_sec`; every tick
reconciles finished beads first, then spawns up to a batch. Ticks are
stateless: markers in bead comments and `bead-<id>` workflow ids absorb races
between overlapping ticks.
"""

from datetime import UTC, datetime, timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_agentic_factory.beads.client import BeadsClient
    from temporal_agentic_factory.beads.models import PollSummary
    from temporal_agentic_factory.beads.poll import poll_once
    from temporal_agentic_factory.beads.temporal import TemporalWorkflows
    from temporal_agentic_factory.settings.load import settings


@workflow.defn(name="beads_poll")
class BeadsPollWorkflow:
    """One poll tick: reconcile finished beads, spawn ready ones."""

    @workflow.run
    async def run(self) -> PollSummary:
        cfg = settings.beads_poller
        return await workflow.execute_activity_method(
            BeadsPollActivity.poll,
            start_to_close_timeout=timedelta(seconds=cfg.tick_timeout_sec),
            retry_policy=RetryPolicy(maximum_attempts=2),
            summary="beads tick",
        )


class BeadsPollActivity:
    @activity.defn
    async def poll(self) -> PollSummary:
        """The tick's I/O: `bd` subprocesses and workflow starts, all here."""
        cfg = settings.beads_poller
        return await poll_once(
            BeadsClient(timeout_sec=cfg.command_timeout_sec),
            TemporalWorkflows(),
            batch_limit=cfg.batch_limit,
            max_in_flight=cfg.max_in_flight,
            orphan_timeout_sec=cfg.orphan_timeout_sec,
            now=datetime.now(UTC),
        )
