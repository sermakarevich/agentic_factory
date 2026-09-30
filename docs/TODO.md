# TODO

Things agreed on and parked. Each has enough of a plan to pick up cold.

## Orphaned coder when the runner dies

The coder subprocess (and, for opencode `--standalone`, its private server
child) outlives the runner when the runner dies hard. The graceful case is
done (Sep 30): the coder starts in its own process group and
`job/process/kill.py` kills the group, so ctrl-c, SIGTERM and a Temporal
worker shutdown take the children too. Left:

**Hard death** (SIGKILL, crash, sleep): nothing in the runner runs. Launch
the coder through a small watchdog that polls its parent pid; when the
parent is gone (parent pid becomes 1) it kills the process group and
exits. Pure Python, works on macOS and Linux. The retry on the next runner
then resumes the session with no leftover coder writing to the workdir.
Test it by killing a fake parent.

## Store: pool size and a batched journal

`JournalCallback.on_event` is one transaction per event, and the store's
engine uses SQLAlchemy's default pool. With `max_concurrent_activities`
coders each writing a few events a second that is fine; at tens of
concurrent jobs, size the pool from settings (`store.pool_size`,
`max_overflow`) and, if writes ever queue up, buffer events in the callback
and flush them every N events or every second in one `executemany`.

## JSON log lines

`JsonLinesCallback` writes one JSON object per event to stdout for the dev
scripts (`--json`). The runner still logs for humans on stderr. When logs go
to a shipper, give the runner the same callback on a file or stdout, and
add the run's ids (session, attempt) to every line.
