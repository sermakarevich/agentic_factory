You are finding the commands of the repo, before any feature code is written.

$rules

Read how the repo runs its tests, its lint and its type check (its
justfile, Makefile, pyproject, package.json, CI config, docs). Run each
command once to see it work. Change no file.

Submit as the output:

- `test`: the command that runs the full test suite from the repo root,
  new tests under `tests/` included, and runs only the given paths when
  test paths are appended to it (`uv run pytest -q`, `npx vitest run`).
- `test_dirs`: the test folders there are now, relative to the repo root.
- `lint` and `typecheck`: the repo's commands, or empty when it has none.
