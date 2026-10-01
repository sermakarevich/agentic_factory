"""The autocode application: what turns a feature spec into tested,
committed code on a branch of a git repo. Plain Python, no engine:
`contract` names what the workflow passes around, `order` puts the units in
build waves, `run` holds where a run's files land and its state, `written`
checks the files a stage was to write, `lock` hashes the tests no coder may
change, `git` and `command` run git and the repo's own commands, `prompts/`
holds the text each job is given."""
