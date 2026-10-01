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
      src/agentic_factory/    # event.py, failure.py, tokens.py, callback.py, logging_setup.py: what every layer shares
        job/                  # contract, callback, engine, session, continuation, ledger, usage, stats, context, outcome, record, defaults
          coders/             # harness base, catalog, decode; claude/ and opencode/ (harness, stream)
          process/            # spawn, kill, environment, workdir, tail: the coder process
          summary/            # contract, prompt, block, parse, repair: the coder's own summary
          report/             # contract, conversation, step, build: the report a model writes over the run
          structured_output/  # contract, prompt, step, extract: the output asked for in the prompt, picked out by a step, saved
        step/                 # contract, reasoning, engine, defaults: the llm step
          judge/              # question, answer, contract, client, catalog, defaults, engine, typesafe: the judge step
          providers/          # client base, catalog; opencode/ (client)
        callbacks/            # log, json_lines, fanout, journal: the callbacks a run's start, events and end go to
        settings/             # settings.toml holds every default; model.py types it; load.py reads it
      scripts/              # run_job.py, run_step.py, run_judge.py: dev entry points behind `just`
      tests/
    distill/                # the application behind the distill workflow: one source into a knowledge-base entry
      pyproject.toml        # package `distill`; depends on factory_settings
      justfile
      src/distill/          # contract, sources (one module per kind), chunking, fetch, verify, topics
        prompts/              # one prompt API over flat .md templates
        settings/             # entry pdf limit, fetch limits and throttles, chunk bounds, verify minimum
      tests/                  # contract, fetch, prompts, settings, topics, verify, boilerplate, chunking, sources
    research/               # the application behind the research workflow: a focus question into a folder of digests
      pyproject.toml        # package `research`; depends on factory_settings
      justfile
      src/research/         # contract (request, candidate, plan, outcomes), run (the state and where a run lands), rank (judge questions, scores, order)
        prompts/              # flat .md templates, one per job, and prompt.py: prompt() and values()
        settings/             # shortlist size, reserve share, lenses, candidate bounds, abstract limit
      tests/                  # contract, rank, run, prompts, settings
  runners/
    temporal_agentic_factory/ # Temporal binding: installs `agentic_factory`
      pyproject.toml        # package `temporal_agentic_factory`
      justfile
      src/temporal_agentic_factory/  # runner (the main-queue process), coders (the one process with a
                              # worker per provider's coder queue), other_coders (its single-instance
                              # check), client, identity: what several roles share
        workflows/            # every Temporal workflow with its activities; failure (JobFailed to
                              # ApplicationError, what their activities share)
          job/                # workflow, child (a job as a child workflow), coder_queue, session,
                              # execute, heartbeat, report, record, search_attributes (the ui's columns)
          structured_output/  # workflow, child, extract: the output asked for in the prompt, picked out by a step
          judge/              # workflow (run_judgment), activity: the judge step for workflows that branch on an answer
          distill/            # workflow, activities (fetch + verify), name (a source's url tail)
          research/           # activities (locate_target, read_candidates), workflow (the chain of jobs
                              # and child distill runs)
        watchers/             # long-running things that watch a state and start workflows
          beads/              # client (bd calls on the database af owns), home ([beads].home), mapping,
                              # models, poll, shell (`bd` subprocess), temporal, tick (the tick activity),
                              # last_check (the query and LastCheck line), trim (old runs deleted),
                              # workflow (the beads_watcher loop), control (start, stop, status),
                              # legacy (the old beads-poll schedule)
        cli/                  # app (the `af` typer app), one module per subject (job: `run`, distill,
                              # research, coders), errors, ids (readable workflow ids), options,
                              # providers (refuses a provider with no settings table), workflows
                              # (status, result, list, cancel, terminate, health)
          beads/              # app (the `af beads` group), opened (the configured database),
                              # database (init, add, list, show, close), poller (ready,
                              # poll --once), watcher (start, stop, restart, status)
        settings/             # server address, activity limits, [providers.<name>] coder limits, one table per workflow
                              # and activity ([job_activity], [distill_workflow],
                              # [research_workflow], [locate_activity], [candidates_activity], ...)
      tests/                  # mirrors src: workflows/<subject>/, watchers/beads/, cli/; fakes.py and
                              # workers.py (a main worker plus one per coder queue) and fake_bd.py
                              # (a scripted `bd`) at the top
    argo_agentic_factory/     # NOT built. README only, see "Why runners/"
  common/
    factory_settings/       # the settings loader (dynaconf + pydantic) and the values every package shares
      pyproject.toml        # package `factory_settings`
      justfile
      src/factory_settings/ # table.py (Table base), load.py (load), vault.py (knowledge-base folders), shared.py + settings.toml ([store] url, [vault] folders)
      tests/
    factory_store/          # the database: schema.py (tables), store.py (async API), clean.py, migrations/ (alembic)
      pyproject.toml        # package `factory_store`
      justfile              # check, migrate, revision
      src/factory_store/
      tests/                # on in-memory sqlite
```

## Responsibilities

**app/** holds the applications, one folder each. An app is one domain
as plain Python: it knows nothing about Temporal and imports no other
app. What two apps would share moves to `common/`.

**app/agentic_factory** owns the job and step domain. It holds the
atomic abstractions:

- **step**: one structured-output request to a model (`Step`,
  `StepResult`, the client per provider, the engine that runs one).
- **job**: one headless coder run (`Job`, `JobResult`, `Event`, failures,
  the harness per coder, the engine that runs one, the session made before
  the first try, continuation for retries, stats, the coder's summary and
  its repair by a step, the conversation rendered from stored events, the
  report step over it, the structured output picked out of the coder's text).
- **callbacks**: the callbacks a run's start, events and end go to (log,
  fanout, the journal that records the try in the store).

Every function here is callable from a test or a script with no engine
running. A new step or job feature is added here and only here.

**app/distill** owns the distill domain: how a source is fetched (one
module per kind behind one `fetch`) and cut into chunks, what each job
is asked (one prompt API over flat `.md` templates, filled by a two-line
`string.Template` renderer in the prompts module), how a finished
entry is checked. The vault's folders live in `common/factory_settings`
(`vault.py`), shared with the research app. It holds no Temporal
and no `agentic_factory` import; the runner's distill workflow orders
its steps.

**app/research** owns the research domain: how a focus question becomes
a folder of digests (the request, the candidates, the judge ranking, the
plan, what each job is asked (`prompts/`), where a run lands). It holds
no Temporal and no `agentic_factory` import; the runner's research
workflow will order its steps. What it shares with distill lives down a
layer: the vault's folders in `common/factory_settings`.

**runners/temporal_agentic_factory** owns the engine binding and the
workflows. It wraps app functions as Temporal activities, implements the
workflows that compose them (the job workflow, the job with structured
output, distill, research) and exposes the CLI (`runner`, `coders`, `run`,
`distill`, `research`, `beads`, `attributes`). It is grouped by role, then by subject
inside each role: `workflows/` holds one folder per workflow with its
activities, `watchers/` the long-running things that watch a state and start
workflows (beads), `cli/` the `af` command with one module per subject, and
`settings/` the runner's settings. A module used by one subject sits in that
subject's folder, one used by one role at that role's root
(`workflows/failure.py`), one used by several roles at the package root
(`client.py`, `coders.py`). The cli imports workflows and watchers, the
watchers import workflows, workflows import neither. Workflows are implemented
here because their code is written against the engine API, and every artifact
a workflow needs (its activities, its settings table, its cli command) lives
in this package. It contains no domain logic: if a function does not mention
Temporal, it belongs in `app/`.

**runners/argo_agentic_factory** is a placeholder with a README only. It
exists to make the split honest: if the engine ever changes (Argo
Workflows on Kubernetes, Prefect, plain cron), only a new folder under
`runners/` is written and `app/` is untouched. It is not on the roadmap.

**common/** holds libraries that two or more apps need, one named
package per folder. Today: `factory_store`, the database (schema,
migrations, async API) that both the app's callbacks and the runner's
activities write through; `factory_settings`, the settings loader and
the values every package shares. A module moves here only when a second app needs it,
never speculatively. `common/` is a folder of packages, not a Python
module named `common`; the rule against `common.py` files still holds
inside every package.

## Dependency direction

```
runners/*  →  app/*  →  common/*
```

Imports point down only. `app/` never imports a runner. `common/`
never imports an app. Two packages in the same layer do not import
each other (`distill` does not import `agentic_factory`); what they
share moves down a layer.

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
- Files are grouped by what they are about, one folder per group, as
  soon as a folder holds more than a dozen files or a group of siblings
  share a prefix (`summary_*.py` is a `summary/` folder). The folder's
  `__init__.py` docstring names the group; the modules keep their plain
  names inside it (`summary/parse.py`, not `summary/summary_parse.py`).
- Name files by behavior in one or two plain words. Never `utils.py`,
  `helpers.py` or `common.py`.
- Directories are namespaces only. Code lives in a named module inside
  each directory.
- Every `__init__.py` is empty of code, so each object has exactly one
  import path. Its only content is a docstring saying what layer this
  folder is and what lives below it.
- One function, one level of abstraction. A function is either a
  sequence of named steps (each a call, read top to bottom as a story) or
  the detail of one step. Filling a default, making a directory and
  parsing a stream do not sit in the same body; each becomes a named
  step whose body is the only place that knows how. Long branches of a
  dispatch become one function per branch behind a table.
- Each step is isolated. It gets what it needs as arguments, returns what
  it made, and touches nothing the other steps use. A step never reaches
  into the caller's locals or leaves work half done for the next step.
- Names say what a function does or returns in plain words, so the
  sequence of steps reads without opening any of them:
  `_with_default_model`, `_read_line_within_limits`, `_job_as_report_request`.
  Never a vague verb: `_prepare`, `_process`, `_handle`, `_drive`,
  `_setup`, `_do`, `_run` (for anything but the engine's entry point).
- One way to get a dependency. A function takes the harness, client or
  store it needs as a required argument; the caller picks it
  (`harness_for`, `client_for`). Never `x = x or make_x()`: an optional
  argument with a fallback is two code paths, one of them untested.
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
  `runners/temporal_agentic_factory` depends on `agentic_factory` and
  `distill` as workspace members.
- `just check` at the root runs every package's `check` (ruff, mypy,
  pytest). Each package's `justfile` is self-contained so a package can
  be checked alone.
- Tests mirror `src/` folder for folder inside each package.
- `just db` starts Postgres (docker compose) and applies the store's
  migrations; `just db-migrate` applies them alone. A schema change is
  `just revision "<what changed>"` in `common/factory_store`, then a
  review of the generated file under `migrations/versions/`.
