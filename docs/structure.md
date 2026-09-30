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
| `schema` | The tables: session, attempt (one try), event, conversation, job, report, outputs. |
| `Store` | The async API over them. One method is one short transaction: start a session or try, append an event, finish a try, save the job, conversation, report and outputs, load any of them back. |
| `clean` | Makes text safe for Postgres (no NUL characters). |
| `migrations/` | Alembic migrations that create and change the tables. |

## app/agentic_factory — the application

Knows nothing about Temporal. Everything runs from a test or a script.

| Component | What it does |
|---|---|
| **shared root** (`event`, `failure`, `tokens`, `callback`) | The words every layer speaks: an `Event` from a coder, the typed failures and whether each is retryable, token counts, the callback interface. |
| **job** | One headless coder run. `contract` is what goes in (`Job`) and comes out (`JobResult`); `engine` runs it: starts the coder, reads its stream as events, watches context and stalls, reads usage back when the stream lost it, parses the coder's summary. |
| **job/coders** | One harness per coder (`claude`, `opencode`): the command line to start it and how to turn its output lines into events. `catalog` picks one by name. |
| **job/process** | Starting, killing and reading a coder process. |
| **job/summary** | The summary the coder writes at the end: its shape, the prompt asking for it, finding and parsing it, repairing it with a step when it is broken. |
| **job/report** | After the job: the conversation rendered from stored events, and the step that judges it and writes a report. |
| **job/outputs** | Typed outputs a workflow needs from a job: the prompt that asks the coder to state them, and the step that picks them out of its last message, or of the whole conversation. |
| **job** helpers (`session`, `continuation`, `ledger`, `context`, `usage`, `record`, `outcome`) | Make the session before try 1, re-prompt for a retry, add up tokens and cost, compact a large context, read lost usage back, write the job row. |
| **step** | One structured-output request to a model. `contract` is `Step` and `StepResult`; `engine` sends it and validates the answer; `providers/` holds one client per API and `catalog` picks one. |
| **callbacks** | Where a run's start, events and end go: the log, JSON lines, the journal that writes events and try rows to the store, and `fanout` that sends to several at once. |
| **settings** | `settings.toml` holds every knob, `model.py` types them, `load.py` reads them. |

## runners/temporal_agentic_factory — the Temporal runner

Wraps the application in Temporal. No domain logic: if a function does
not mention Temporal, it belongs in the app.

| Component | What it does |
|---|---|
| `cli` (`factory`) | `runner` starts the poller, `run` starts one job and waits (`--outputs <schema>` asks for typed outputs), `attributes` registers the search attributes on the server. |
| `runner` | The worker: connects, builds the store and the callbacks, registers the activities and workflows, polls the task queue. |
| `workflows/job` | The job workflow: make the session, run the job activity with retries, report, record. Deterministic, no I/O. |
| `workflows/outputs` | The job-with-outputs workflow: the job asked for its outputs, then the extraction activity; fails when they were not stated. |
| `activities/` | One activity per app call (session, job, report, outputs, record). `failure` maps app failures to Temporal retry behaviour; `heartbeat` keeps a long job alive. |
| `search_attributes` | The columns and filters the Temporal UI shows for a job. |
| `client`, `identity`, `settings` | Connecting to the server, naming the runner (`host:pid:sha`), where the server is and how long activities may take. |
