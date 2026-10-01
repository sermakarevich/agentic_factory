"""The Temporal runner, grouped by subject: one folder per workflow with its
activities (job, structured_output, judge, distill). Every subject uses the
two root modules: failure.py (JobFailed to ApplicationError) and
heartbeat.py (liveness and context size while a job runs)."""
