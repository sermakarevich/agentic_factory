"""The distill application: what turns one source (url, pdf, video, repo)
into a knowledge-base entry. Plain Python, no engine: `fetch` gets the source
and cuts it into chunks, `prompts/` holds the text each job is given,
`verify` checks the entry a job wrote, `contract` names what the workflow
passes around."""
