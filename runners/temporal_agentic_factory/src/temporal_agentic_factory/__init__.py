"""The Temporal runner, grouped by role, then by subject inside each role:
workflows/ (every workflow with its activities), watchers/ (long-running
things that watch a state and start workflows), cleaner/ (the schedule that
deletes old runs), cli/ (the `af` command) and settings/. The root holds the
processes and what they share: runner.py (the main queue's process), coders.py
(the coder queues' process), other_coders.py (the one-coders-process check),
client.py (the Temporal client), schedules.py (a Schedule's lifecycle, for the
beads poll and the cleaner) and identity.py (the process id Temporal shows)."""
