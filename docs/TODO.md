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

## Recover usage opencode lost at exit

When opencode drops its last `step_finish` (a race with process exit,
see DESIGN quirks) the result has `usage_known=False` and the tokens of
the last turn are missing. opencode keeps every session, with per-message
tokens and cost, in its own store on disk. After the process has exited,
read the session back through `opencode api session.messages` (or the
files) and fill the totals from there. Read only; the store is opencode's.
Do it in the harness after `end_of_stream()`, behind a setting, and test it
against a session created by a smoke run. Until then, sum `usage_known`
rows separately from the rest when reporting cost.

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
