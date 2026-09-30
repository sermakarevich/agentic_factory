# agentic_factory — codebase layout

Monorepo, one `uv` workspace. Three top-level folders with one
responsibility each. Concepts are defined in [DESIGN.md](DESIGN.md).

```
agentic_factory/
  pyproject.toml            # uv workspace root: lists members, shared dev tools
  justfile                  # delegates to each package's justfile (check, test, run, temporal, db)
  docker-compose.yml        # Postgres for the store: `just db`
  docs/
    DESIGN.md               # abstractions, needs, decisions
    DECISIONS.md            # decisions log: what was chosen, what was rejected, why
    CODEBASE.md             # this file
  app/
    agentic_factory/          # the application: everything that is not an engine
      pyproject.toml        # package `agentic_factory`
      justfile
      src/agentic_factory/    # job/, step/, observe/ (log, fanout, journal); settings/settings.toml holds every default
      scripts/              # run_job.py, run_step.py: dev entry points behind `just`
      tests/
  runners/
    temporal_agentic_factory/ # Temporal binding: installs `agentic_factory`
      pyproject.toml        # package `temporal_agentic_factory`
      justfile
      src/temporal_agentic_factory/  # activities/, workflows/, settings/ (server address, activity limits)
      tests/
    argo_agentic_factory/     # NOT built. README only, see "Why runners/"
  common/
    factory_store/          # the database: schema.py (tables), store.py (async API), migrations/ (alembic)
      pyproject.toml        # package `factory_store`
      justfile              # check, migrate, revision
      src/factory_store/
      tests/                # on in-memory sqlite
```

## Responsibilities

**app/agentic_factory** owns the domain. It knows nothing about Temporal.
It holds the atomic abstractions as plain Python:

- **step**: one structured-output request to a model (`Step`,
  `StepResult`, the client per provider, the engine that runs one).
- **job**: one headless coder run (`Job`, `JobResult`, `Event`, failures,
  the harness per coder, the engine that runs one, the session made before
  the first try, continuation for retries, stats, the coder's summary and
  its repair by a step, the conversation rendered from stored events, the
  report step over it).
- **observe**: the observers a run's events go to (log, fanout, the
  journal that writes them to the store).
- **tools**: the tools exposed to steps and jobs (ask_human, web fetch,
  and any MCP server config the harness is handed).
- plain functions a workflow needs around a job (worktree, bead update),
  the artifact store, and the Langfuse adapter.

Every function here is callable from a test or a script with no engine
running. A new step, job or tool is added here and only here.

**runners/temporal_agentic_factory** owns the engine binding and the
workflows. It wraps `agentic_factory` jobs and steps as Temporal
activities, implements the workflows that compose them (the job workflow,
multi-step ones, the watcher loop), registers schedules, and exposes the CLI
(`start`, `run`, `ask`). Workflows are implemented here because their
code is written against the engine API. It contains no domain logic:
if a function does not mention Temporal, it belongs in `app/`.

**runners/argo_agentic_factory** is a placeholder with a README only. It
exists to make the split honest: if the engine ever changes (Argo
Workflows on Kubernetes, Prefect, plain cron), only a new folder under
`runners/` is written and `app/` is untouched. It is not on the roadmap.

**common/** holds libraries that two or more apps need, one named
package per folder. Today: `factory_store`, the database (schema,
migrations, async API) that both the app's observers and the runner's
activities write through. A module moves here only when a second app needs it,
never speculatively. `common/` is a folder of packages, not a Python
module named `common`; the rule against `common.py` files still holds
inside every package.

## Dependency direction

```
runners/*  →  app/*  →  common/*
```

Imports point down only. `app/` never imports a runner. `common/`
never imports an app. Two packages in the same layer do not import
each other; what they share moves down a layer.

## Structure rules

From the knowledge-base recipe `coding/structure`, applied to every
package here:

- Favor simplicity, readability, evolvability and maintainability over
  cleverness. Avoid complexity.
- Organize code top-down for progressive disclosure: lower-level code
  lives in folders below the code that calls it.
- Calls and imports point down only. No cycles, no upward imports.
- A module used by two or more siblings moves up to their nearest
  common ancestor.
- Cross-cutting modules stay at the package root. Shared code is never
  nested under one caller.
- One file, one job. Small files. Add a sibling file instead of a
  second responsibility.
- Name files by behavior in one or two plain words. Never `utils.py`,
  `helpers.py` or `common.py`.
- Directories are namespaces only. Code lives in a named module inside
  each directory.
- Every `__init__.py` is empty of code, so each object has exactly one
  import path. Its only content is a docstring saying what layer this
  folder is and what lives below it.
- No hardcoded knobs. A value that tunes behaviour (a size, width,
  limit, timeout, delay, default) lives in the package's
  `settings/settings.toml` with a typed field in `settings/model.py` and
  a one-line comment saying what it does. Never a module constant, never
  an inline literal. Facts of a protocol or contract (an env var name, a
  header, a JSON key, a regexp, a prompt) stay in code as named
  constants beside their one user, grouped in an enum when there are
  several of a kind.

How to apply when reviewing or refactoring:

1. Map the target top-down: entry points first, then what they call.
2. Flag every violation with file path, rule broken and the concrete
   move.
3. Fix one violation per change, review-sized, tests after each move.
4. Do not add abstractions, comments or docstrings to explain bad
   structure. Move the code instead.

## Tooling

- `uv` workspace: the root `pyproject.toml` lists members under
  `[tool.uv.workspace]`; each package declares its own dependencies.
  `runners/temporal_agentic_factory` depends on `agentic_factory` as a
  workspace member.
- `just check` at the root runs every package's `check` (ruff, mypy,
  pytest). Each package's `justfile` is self-contained so a package can
  be checked alone.
- Tests mirror `src/` folder for folder inside each package.
- `just db` starts Postgres (docker compose) and applies the store's
  migrations; `just db-migrate` applies them alone. A schema change is
  `just revision "<what changed>"` in `common/factory_store`, then a
  review of the generated file under `migrations/versions/`.
