"""The `af` command layer: the typer app (`app.py`), what every submit command
shares (errors, ids, admission) and the commands on existing workflows.

Submit:      af run "prompt" [--detach] [--workflow-id ID] [--force] | af distill URL | af research
Pull (beads): af beads ready | af beads poll [--once] | af beads schedule | af beads unschedule
Inspect:     af status ID | af result ID | af list [--status Running] [--type job]
Stop:        af cancel ID | af terminate ID
Serve:       af runner (polls task queues) | af health | af attributes (once per server)
"""
