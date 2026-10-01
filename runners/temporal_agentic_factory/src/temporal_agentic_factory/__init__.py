"""The Temporal runner, grouped by role, then by subject inside each role:
workflows/ (every workflow with its activities), watchers/ (long-running
things that watch a state and start workflows), cli/ (the `af` command) and
settings/. The root holds what several roles share: runner.py (the process),
client.py (the Temporal client), identity.py (the runner id) and capacity.py
(free slots under the global job cap)."""
