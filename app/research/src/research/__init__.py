"""The research application: what turns a focus question into a folder of
digests under research_topics/<topic>/research/<target/>. Plain Python, no
engine: `contract` names what the workflow passes around, `run` holds one run's
state and where it lands, `rank` judges and orders the candidates, `prompts/`
holds the text each job is given."""
