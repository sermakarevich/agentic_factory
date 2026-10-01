"""The `af` command layer: the typer app (`app.py`), one module per subject's
commands (job, distill, research, tutorial, beads), what every submit command shares
(errors, ids, options, providers) and the commands on existing workflows.

Submit:      af run "prompt" [--detach] [--workflow-id ID] | af distill URL | af research
             | af tutorial "topic" [--name N] [--formats md,ipynb] [--level L]
Pull (beads): af beads start | stop | restart | status | ready | poll --once
Inspect:     af status ID | af result ID | af list [--status Running] [--type job]
Stop:        af cancel ID | af terminate ID
Serve:       af runner (main queue, many may run) | af coders (coder queues, one per machine)
             | af health | af attributes (once per server)
"""
