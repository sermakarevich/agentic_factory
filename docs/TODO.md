# TODO

Things agreed on and parked. Each has enough of a plan to pick up cold.

## Orphaned coder when the runner dies

The coder subprocess (and, for opencode `--standalone`, its private server
child) outlives the runner. Two cases:

1. **Graceful stop** (ctrl-c, SIGTERM, Temporal worker shutdown): the engine's
   kill path runs but kills only the coder process, not its children. Start
   the coder with `start_new_session=True` so it and its children form one
   process group, and kill the group (`os.killpg`) in `_kill`. Temporal
   cancels running activities on shutdown, so the engine's cleanup runs.
2. **Hard death** (SIGKILL, crash, sleep): nothing in the runner runs. Launch
   the coder through a small watchdog that polls its parent pid; when the
   parent is gone (parent pid becomes 1) it kills the process group and
   exits. Pure Python, works on macOS and Linux. The retry on the next runner
   then resumes the session with no leftover coder writing to the workdir.

Do both together. Test 1 with a fake coder that spawns a child and check the
child is gone after a `Stalled`; test 2 by killing a fake parent.

## Store: pool size and a batched journal

`JournalCallback.on_event` is one transaction per event, and the store's
engine uses SQLAlchemy's default pool. With `max_concurrent_activities`
coders each writing a few events a second that is fine; at tens of
concurrent jobs, size the pool from settings (`store.pool_size`,
`max_overflow`) and, if writes ever queue up, buffer events in the callback
and flush them every N events or every second in one `executemany`.

## `just revision` needs the database url

`common/factory_store`'s `revision` recipe does not set `FACTORY_STORE_URL`
like `migrate` does, so autogenerate fails with `KeyError`. Set it the same
way in the recipe.
