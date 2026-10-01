"""The job workflow and its activities: a session made once, the submission
schema saved and the job asked to submit its result, the job run with
heartbeats on its provider's coder queue, the coder's submission read (and
asked again when it is missing), its row in the store, the search attributes
the UI shows, and the helpers that run a job as a child workflow."""
