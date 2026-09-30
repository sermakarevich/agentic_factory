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

## Outcome layer 6: infer the summary from the trace

No block at all, or a killed run: a step reads a condensed trace (turn text,
tool names and arguments, error flags, no tool outputs) and produces the
summary. Needs the events persisted across tries first: a journal observer
appending events as jsonl per session id under the data dir.
