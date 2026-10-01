"""The job with structured output: the workflow that asks a job to submit a
typed answer through `af output submit`, the submission activities (the
schema saved, what was submitted read back), the extraction activity that
picks it out of what the job wrote when it submitted nothing, and the
helper that runs it as a child workflow."""
