# Structure

What each application is made of, in one screen. Details live in
[CODEBASE.md](CODEBASE.md) (every file) and [DESIGN.md](DESIGN.md) (why).

```
runners/temporal_agentic_factory   runs jobs on Temporal
        │ imports
app/agentic_factory                runs one job or one step, no engine
        │ imports
common/factory_store               the database
common/factory_settings            the settings loader
```

## common/factory_settings — the settings loader

| Component | What it does |
|---|---|
| `load` | Reads a package's `settings.toml`, then `settings.local.toml`, then `AF_*` environment variables, into a typed model. |
| `Table` | The base of every typed settings table. An unknown key is an error. |
| `shared` | The one value every package needs: the store URL. |

## common/factory_store — the database

| Component | What it does |
|---|---|
| `schema` | The tables: session, attempt (one try), event, conversation, job, report, structured_output. |
| `Store` | The async API over them. One method is one short transaction: start a session or try, append an event, finish a try, save the job, conversation, report and structured output, load any of them back. |
| `clean` | Makes text safe for Postgres (no NUL characters). |
| `migrations/` | Alembic migrations that create and change the tables. |

## app/agentic_factory — the application

Knows nothing about Temporal. Everything runs from a test or a script.

| Component | What it does |
|---|---|
| **shared root** (`event`, `failure`, `tokens`, `callback`) | The words every layer speaks: an `Event` from a coder, the typed failures and whether each is retryable, token counts, the callback interface. |
| **job** | One headless coder run. `contract` is what goes in (`Job`) and comes out (`JobResult`); `engine` runs it: starts the coder, reads its stream as events, watches context and stalls, reads usage back when the stream lost it. |
| **job/coders** | One harness per coder (`claude`, `opencode`): the command line to start it and how to turn its output lines into events. `catalog` picks one by name. |
| **job/process** | Starting, killing and reading a coder process. |
| **job/report** | The report the coder submits at the end (task, done with evidence, not done, problems, verdict), and the one code makes for a job the engine could not finish. |
| **job/submission** | How a job hands back its result: the one submission schema (report, and output when a workflow asked for one), the prompt asking the coder to run `af output submit`, the check with path-named errors, saving and reading it, the reminder. |
| **job** helpers (`session`, `continuation`, `ledger`, `context`, `usage`, `record`, `outcome`) | Make the session before try 1, re-prompt for a retry, add up tokens and cost, compact a large context, read lost usage back, write the job row. |
| **step** | A call to a model that is not a coder: the judge step (`step/judge`). |
| **callbacks** | Where a run's start, events and end go: the log, JSON lines, the journal that writes events and try rows to the store, and `fanout` that sends to several at once. |
| **settings** | `settings.toml` holds every knob, `model.py` types them, `load.py` reads them. |

## runners/temporal_agentic_factory — the Temporal runner

Wraps the application in Temporal. No domain logic: if a function does
not mention Temporal, it belongs in the app.

| Component | What it does |
|---|---|
| `cli` (`factory`) | `runner` starts the poller, `run` starts one job and waits (`--structured-output <schema>` asks for a structured output), `attributes` registers the search attributes on the server. |
| `runner` | The worker: connects, builds the store and the callbacks, registers the activities and workflows, polls the task queue. |
| `workflows/job` | The job workflow: make the session, ask for the submission, run the job activity with retries, read the submission and remind, record. Takes an optional output schema; fails when it asked for one and none was submitted. Deterministic, no I/O. |
| `activities/` | One activity per app call (session, job, submission, record). `failure` maps app failures to Temporal retry behaviour; `heartbeat` keeps a long job alive. |
| `search_attributes` | The columns and filters the Temporal UI shows for a job. |
| `client`, `identity`, `settings` | Connecting to the server, naming the runner (`host:pid:sha`), where the server is and how long activities may take. |
