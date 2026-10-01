Rules for every autocode job:

- You work in the git repo `$repo`, on its branch `$branch`, building the
  feature `$feature`. Stay inside the repo; keep scratch files in `.local/`.
- Never run a git command that changes anything: no commit, checkout,
  stash or reset (reading, as `git log` and `git diff`, is fine). The
  workflow commits each stage's work after it checks it.
- Favor simplicity, evolvability and maintainability over cleverness.
  Prefer readable code to comments and docstrings. Avoid complexity and
  needless abstractions. Follow the repo's own layout, naming and style.
- Tests are read-only after creation: once the tests stage is done, no job
  changes, deletes or adds a file under `$tests_dir/`. Make the code pass
  them; never bend a test to the code.
- Do only your own job's part; leave what other jobs own to them.
- Set the verdict to `done` only when your job is fully done. Anything left
  undone goes in `not_done`, anything that blocked you in `problems`.
