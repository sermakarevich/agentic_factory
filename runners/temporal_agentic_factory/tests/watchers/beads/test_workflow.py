import asyncio
import uuid

from temporal_agentic_factory.watchers.beads.workflow import BeadsWatcherWorkflow, WatcherRun
from temporal_agentic_factory.workflows.job.search_attributes import LAST_CHECK
from tests.watchers.beads.fake_watcher import INTERVAL_SEC, Ticks, config, until, watching


async def test_the_loop_ticks_then_sleeps_the_interval_before_the_next_tick() -> None:
    ticks = Ticks()
    async with watching(ticks) as watch:
        handle = await watch.client.start_workflow(
            BeadsWatcherWorkflow.run,
            WatcherRun(config=config()),
            id=f"w-{uuid.uuid4()}",
            task_queue=watch.queue,
        )
        await until(watch, lambda: ticks.ticks == 1)
        await asyncio.sleep(0.3)
        assert ticks.ticks == 1  # the timer holds the next tick back
        await until(watch, lambda: ticks.ticks >= 2, step_sec=INTERVAL_SEC)
        check = await handle.query(BeadsWatcherWorkflow.last_check)
        assert check is not None
        assert (check.spawned, check.skipped, check.error) == (1, 1, "")
        attributes = (await handle.describe()).typed_search_attributes
        assert attributes.get(LAST_CHECK) == check.line()
        assert ticks.trims == 1  # once at the first start
        await handle.terminate()


async def test_a_failing_tick_is_recorded_and_the_loop_goes_on() -> None:
    ticks = Ticks(failing={1})
    async with watching(ticks) as watch:
        handle = await watch.client.start_workflow(
            BeadsWatcherWorkflow.run,
            WatcherRun(config=config()),
            id=f"w-{uuid.uuid4()}",
            task_queue=watch.queue,
        )
        await until(watch, lambda: ticks.ticks == 1)
        await asyncio.sleep(0.3)
        failed = await handle.query(BeadsWatcherWorkflow.last_check)
        assert failed is not None and "bd is down" in failed.error
        assert (await handle.describe()).typed_search_attributes.get(LAST_CHECK) == "tick failed"
        await until(watch, lambda: ticks.ticks >= 2, step_sec=INTERVAL_SEC)
        await asyncio.sleep(0.3)
        recovered = await handle.query(BeadsWatcherWorkflow.last_check)
        assert recovered is not None and recovered.error == "" and recovered.spawned == 1
        await handle.terminate()


async def test_the_run_continues_as_new_after_checks_per_run_ticks() -> None:
    ticks = Ticks()
    async with watching(ticks) as watch:
        handle = await watch.client.start_workflow(
            BeadsWatcherWorkflow.run,
            WatcherRun(config=config(checks_per_run=2)),
            id=f"w-{uuid.uuid4()}",
            task_queue=watch.queue,
        )
        first_run = handle.result_run_id
        await until(watch, lambda: ticks.ticks >= 3, step_sec=INTERVAL_SEC)
        latest = watch.client.get_workflow_handle(handle.id)
        described = await latest.describe()
        assert described.run_id != first_run
        assert ticks.trims == 2  # at the first start and before the new run, not at its start
        carried = await latest.query(BeadsWatcherWorkflow.last_check)
        assert carried is not None
        await latest.terminate()
