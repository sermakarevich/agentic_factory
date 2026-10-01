import asyncio

from temporal_agentic_factory.watchers.beads.control import (
    ABSENT,
    start_watcher,
    stop_watcher,
    watcher_status,
)
from tests.watchers.beads.fake_watcher import Ticks, config, until, watching

WATCHER_ID = "beads-watcher-test"


async def test_start_is_idempotent_and_status_shows_the_last_check() -> None:
    ticks = Ticks()
    async with watching(ticks) as watch:
        assert await start_watcher(watch.client, WATCHER_ID, watch.queue, config()) is True
        assert await start_watcher(watch.client, WATCHER_ID, watch.queue, config()) is False
        await until(watch, lambda: ticks.ticks == 1)
        await asyncio.sleep(0.3)
        found = await watcher_status(watch.client, WATCHER_ID, query_timeout_sec=5)
        assert found.running and found.status == "RUNNING"
        assert found.last_check is not None and found.last_check.spawned == 1
        await watch.client.get_workflow_handle(WATCHER_ID).terminate()


async def test_stop_cancels_the_watcher_and_status_then_says_it_does_not_run() -> None:
    ticks = Ticks()
    async with watching(ticks) as watch:
        await start_watcher(watch.client, WATCHER_ID, watch.queue, config())
        await until(watch, lambda: ticks.ticks == 1)
        assert await stop_watcher(watch.client, WATCHER_ID, wait_sec=10) is True
        found = await watcher_status(watch.client, WATCHER_ID, query_timeout_sec=5)
        assert not found.running and found.status == "CANCELED"
        assert await start_watcher(watch.client, WATCHER_ID, watch.queue, config()) is True
        await watch.client.get_workflow_handle(WATCHER_ID).terminate()


async def test_a_missing_watcher_is_absent_and_stops_cleanly() -> None:
    async with watching(Ticks()) as watch:
        found = await watcher_status(watch.client, WATCHER_ID, query_timeout_sec=5)
        assert (found.running, found.status) == (False, ABSENT)
        assert await stop_watcher(watch.client, WATCHER_ID, wait_sec=1) is True
