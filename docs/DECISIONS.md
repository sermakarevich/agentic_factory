# agentic_factory — decisions log

Raw material for the write-up. One entry per decision: what was chosen,
what was tried or considered instead, why, and what proved it. Newest
entries go at the end of their section. Dates are 2026.

Vocabulary used below: a **step** is one structured-output request to a
model; a **job** is one headless coder run (`claude -p`, `opencode run`);
a **try** is one Temporal attempt of the job activity; a **run** is one
execution of a workflow; the **runner** is the process that polls task
queues.

## 1. Job: driving a coder CLI as one activity

### Parsing the stream line by line

- **Chosen.** The coder is a subprocess writing JSON lines. A `Harness`
  per coder turns each line into zero or more normalized `Event`s named
  after LangChain message kinds (`session`, `ai`, `tool`, `rate_limit`,
  `finished`, `compaction`, `unknown`). The harness is pure translation:
  sync, no process started there. The engine is the only async piece.
- **Why events, not the coder's own session.** The two coders keep their
  history in different private stores (a `.jsonl` per session for claude,
  a SQLite database for opencode). Reading those means depending on
  versioned, undocumented layouts. The stream is the contract the coders
  publish. Everything downstream (heartbeats, journal, stats, report) is
  built from the same event stream, so adding a coder is one harness.
- **Unknown lines are kept, not dropped.** A line with no rule becomes an
  `unknown` event with the text as content, so a changed stream format is
  debuggable from the log instead of silently losing data.
- **Failures are typed, one per retry rule.** `RateLimited(resets_at)`,
  `ContextPressure`, `Stalled`, `TimedOut`, `ProviderError`,
  `NetworkError`, `CoderCrashed`. Raised only when no result exists. The
  runner maps each class to a Temporal `ApplicationError` typed by name,
  and `RateLimited` sets the next retry delay to the reset time. Retry
  policy therefore never appears in workflow code.
- **Quirks that shaped the harnesses** (all found by live smoke runs):
  opencode needs `--standalone` or the last `step_finish` never arrives,
  and even then the last line can be lost in a race with exit, so the
  harness closes the run from `end_of_stream()` using the totals seen.
  opencode takes its working directory from `$PWD`, not the real cwd, so
  the engine sets both. Its first standalone start takes about 45 s, so
  the stall timeout must stay above that. claude waits on an open stdin,
  so every coder is started with stdin closed. claude's `--allowedTools`
  is variadic and swallows the prompt, so the prompt goes right after
  `-p`. claude emits `rate_limit_event` on every run once usage passes a
  warning threshold; only status `rejected` is a failure.

### Continuation: the session is made before try 1

- **Chosen.** A `create_session` activity makes the coder session before
  the first try, and every try starts the coder with the same session id.
  Nothing on our side decides between "resume" and "start over": the
  session holds whatever the earlier try did, possibly nothing.
- **Why.** Temporal keeps the activity result in history, so a retry of
  the job activity never makes a second session, and a runner restart
  resumes the same session on another process.
- **Per coder.** claude has no single flag: `--session-id` starts and
  fails on a second run, `--resume` continues and fails on a new id, both
  together are refused. The harness picks the flag by whether a transcript
  file for the id exists. opencode `--session` must name an existing
  session, so the session is made with `opencode api session.create`.
  Tried and rejected: inserting a row with our id into opencode's
  `session_v2` table. It works but writes into a private, versioned store
  whose rows must match the project.
- **What a retry sends.** Three options were weighed. Sending the bare
  prompt again was tried on claude: it redid the first step of a killed
  job and only afterwards noticed the earlier attempt. "Continue where
  you left off" reads best to the coder but needs a probe of whether the
  session has any message, since a try can die before the coder wrote one
  and "continue" in an empty session ends as a false success; the probe
  is a file check on claude but an API call per retry on opencode.
  Chosen: a short "try N, continuation" header plus the original prompt.
  It needs no probe, every try on every coder sends the same form, and
  the header explains why the task appears twice. Open: whether coders
  then reliably skip finished work; the kill tests' prompt itself said
  to skip.
- **Kept as its own module.** `job/continuation.py` stays in the app, not
  the runner, because the header is prompt wording the coder sees.

### Callbacks: observers, not return values

- **Chosen.** The engine takes one `Observer` with one method,
  `on_event(Event)`, and does not know who listens. The runner fans out to
  a heartbeat observer (Temporal liveness plus the context size of the
  last turn), a log observer and a journal observer (the store).
- **Why.** The engine stays engine-agnostic and testable with no Temporal
  and no database. Adding Langfuse later is one more observer on the same
  stream.
- **Heartbeat details are our own model** (time of last event, event
  count, context size), so the next try can read the previous try's
  context size from `activity.info()` and decide whether to compact
  before resuming.

### Autocompaction: always on, threshold is a setting

- **Chosen.** Two thresholds in settings: compact at 150k tokens, kill at
  200k. Compaction is not a `Job` field, so no caller can turn it off or
  move it; the kill limit stays on the job because it is a resource bound
  like the timeout. The engine computes the context of every model turn
  as input plus cache read plus cache write tokens.
- **Per coder.** opencode can be compacted beside a live run
  (`session.compact` through its API; applied at the next step in about
  3 s, 19 messages became 4). claude cannot be told during a run, so the
  command passes `--autocompact <threshold>` and claude does it itself;
  `claude -p /compact --resume <id>` is a separate run (about 12 s) used
  only before a resume. On resume the engine compacts first when the
  session's last known context is at or above the threshold.
- **Best effort.** A compaction request is reported as a `compaction`
  event, succeeded or failed, and the run continues either way. The kill
  limit is the backstop, and after `ContextPressure` Temporal retries with
  the same session.

### Persistence: one row per event in Postgres

- **Chosen.** `common/factory_store`: SQLAlchemy Core tables, alembic
  migrations, one async `Store` API. Tables `session`, `attempt`,
  `event`, `conversation`, `report`. The `event` row holds the whole
  `Event` as json (raw line included) with the try number and the coder's
  timestamp. Written live by a `JournalObserver`.
- **Why a database and not files.** A retry, a runner restart or a
  judgement after the fact all need the events of every try, and a
  workflow's tries can run on different processes. Files keyed by run id
  reinvent a table with worse concurrency.
- **Ordering by row id.** The bigserial id is the order of the session
  across tries and restarts. A sequence number in memory restarts with
  the process; timestamps from two tries can overlap when an orphaned
  coder is still writing. Attempt and timestamp are stored too, for
  display.
- **Postgres in production, SQLite in tests.** The schema uses
  `with_variant` so json is `JSONB` on Postgres and `JSON` on SQLite, and
  the id is `BigInteger` with an `Integer` variant for SQLite autoincrement.
  Tests run on `sqlite+aiosqlite:///:memory:` through the same schema, so
  no test needs the database. Postgres runs from the repo's docker compose
  (`just db`).
- **Where it lives.** `common/` because both the app (journal observer)
  and the runner (activities) write through it. Dependency direction is
  runners → app → common; common imports neither.
- **Considered and parked.** Reusing Langfuse's database as the store:
  rejected for now, Langfuse is a viewer of the stream, not the source of
  truth. Giving Temporal's own database a second use: rejected, history is
  Temporal's.

### The conversation and the report

- **Chosen.** At the end of the last try, the stored events are rendered
  as one transcript: a header per try, the model's text, its tool calls
  with clipped arguments, tool outputs clipped in the middle (head and
  tail kept, so what started and ended a long output is visible), rate
  limits, compactions, the finish line. Clip sizes are settings. A report
  step reads it and writes a `JobReport`: task, done (with the evidence
  seen), not done, problems, and a verdict `done | partial | failed |
  unknown`. It is told that a claim by the coder is not evidence and a
  command output is.
- **Why a report over the whole session, not the coder's summary.** The
  engine only knows whether the run completed. Whether the work is done is
  judged in layers, cheap first: stats counted from the stream (turns,
  tool calls, failed tool calls), then the coder's own summary block
  (a claim), then a model reading the whole transcript across every try.
  An earlier plan inferred only the summary from a condensed trace; the
  transcript of every try replaced it once events were stored anyway.
- **The report runs whatever happened to the job.** A permanently failed
  job gets a report on its failure. A failed report step is not fatal:
  the outcome just has no report.
- **The coder's summary block** is asked for by wrapping every prompt in
  the engine (once, so every try gets the same wording). Detection is a
  regexp for the key over every `ai` event, last hit wins; fences are
  ignored because coders drop the closing one (seen on opencode). Parsing
  is strictest first, then a lenient pass for the mistakes seen (bare key,
  trailing commas, Python literals). A block that was found but did not
  parse is repaired by a step with a system prompt that forbids inventing
  facts, run with a silent observer so its tokens do not pollute the
  heartbeat's context reading.

## 2. Step: structured output that is useful

- **Chosen.** `Step` carries a prompt, a system prompt and a JSON schema
  chosen by the caller (`SomeModel.model_json_schema()`); `StepResult`
  holds the answer as a dict and `parse(SomeModel)` gives the typed object
  or raises `BadOutput`. One request, one JSON answer, no tools.
- **Why the caller owns the schema.** The step engine does not know what
  a report or a status looks like; the workflow that needs typed data
  between two jobs does. Schemas go in strict mode, so the models forbid
  extra fields and the provider rejects a wrong shape instead of us.
- **Same shape as the job package.** `contract.py`, `client.py` (the base,
  as `harness.py` is for coders), `catalog.py`, `engine.py`, one folder per
  provider. The step engine emits the same events (`ai`, `finished`) to
  the same observers, so a step and a job look alike to whoever listens.
- **Provider.** The OpenCode Go API, covered by the same subscription as
  the opencode CLI, through the `openai` SDK. The protocol is picked from
  the model name: chat completions by default, Responses for muse-spark,
  grok and gpt. Learned by probes: the SDK works once the user agent is
  overridden, each request needs a fresh `x-opencode-session` header,
  reasoning models spend most output tokens thinking so `max_tokens` must
  leave room, and a reasoning effort of `low` cut glm-5.3-flash from 30 s
  to 6 s. No retries in the client: Temporal retries.
- **Where steps are used.** Repairing a coder's summary block, the report
  over a session, and, planned, any typed judgement between two jobs.
  Renamed from "llm call" to "step" in Sep 2026 so the vocabulary matches
  the workflow's building blocks.

## 3. Runner: the Temporal binding

- **There is no "worker" in the app** (Sep 2026). A first cut had a
  `worker/` package: definitions with before and after step lists, a state
  threaded through Python steps, an in-process chain, mirrored by a
  Temporal workflow. It was dropped: the chain was written twice, nothing
  but a test called the app's copy, and the Python steps competed with the
  llm step for the name. What surrounds a job (workdir, worktree, bead
  status, tests, verdict) is written as Temporal workflows composing two
  activities, and any Python such a workflow needs lives in the app as a
  plain function called from an activity. The process that polls task
  queues is the **runner**.
- **Activities are one-line wrappers.** `create_session`, `execute_job`,
  `execute_step`, `build_report`. Retries never appear in workflow code;
  each failure class carries its own rule. The job activity reads its
  attempt number and the previous try's heartbeat from `activity.info()`.
- **Two timeouts, engine first.** Heartbeat timeout is the stall time
  plus a margin, start-to-close is the job timeout plus a margin, so the
  engine kills first and Temporal is the backstop.
- **Settings split.** Job fields stay in the app's settings because they
  describe a job whatever engine runs it. The runner has its own table
  for the engine's part: server address, namespace, task queue, activity
  margins, retry policy, concurrency. App code is imported inside
  `imports_passed_through()` because settings load on import and the
  workflow sandbox would rerun that.
- **Dev server, not docker.** Temporal is the `temporal` CLI dev server:
  one binary, history in a SQLite file, UI on port 8233. Clients use
  `127.0.0.1:7233`, never `localhost`: on macOS that resolves to IPv6
  first and the server is IPv4 only, so gRPC hangs. Postgres for the
  store is the one docker service; the runner stays on the host because
  it needs the coder CLIs, their auth stores and the worktrees.
- **UI on the tailnet.** `just temporal-tailscale` binds the UI to every
  interface (localhost and the Tailscale IP) and keeps gRPC on 127.0.0.1.
  Binding the UI to the Tailscale IP alone was tried first and lost
  localhost, since the dev server takes one UI address. `tailscale serve` would be
  cleaner (HTTPS, a name) but needs the feature enabled on the tailnet by
  its admin.
- **Proven by the restart test.** Runner killed mid-job and restarted:
  Temporal failed the try with a heartbeat timeout, try 2 started with
  attempt 2 in the session made before try 1, and the coder resumed it
  saying it would not redo the work. Open: killing the runner does not
  kill the coder, which kept working as an orphan; the fix is a process
  group plus a watchdog (see TODO).
- **Workflows are Python, not YAML.** Graphs are code; a data-driven DAG
  interpreter can be added later if needed. Beads is an input source and
  an output target, not the internal state store.

## 4. Cross-cutting

### One level of abstraction per function

**Chosen.** Every function is either a sequence of named steps or the
detail of one step. The job engine's `run` reads as prepare, compact when
the session is large, drive the coder, summarize, result; each step's body
is the only place that knows how it is done. The context watch (compaction
request, context pressure) and the coder environment got their own modules
because two callers need them.

**Rejected.** One long function with comments marking its phases. The
comments drift, the phases share locals, and a reader cannot tell which
lines are the plan and which are its details. Also rejected: extracting by
line count alone. A dispatch of one-line branches is one level already and
stays as it is, however long.

**Why.** A function whose body mixes filling a default model, making a
directory and parsing a stream has no shape a reader or a model can hold.
Named steps give the plan in six lines and the details behind six names.

### Steps are named by what they do

**Chosen.** A step's name says what it does or returns in plain words:
`_with_default_model`, `_read_line_within_limits`, `_parse_or_repair_summary`.
The sequence in `run` reads without opening any step.

**Rejected.** Vague verbs (`_prepare`, `_drive`, `_show`, `_complete`).
They came out of the first pass at the engine and were sent back: a step
called `_prepare` hides three unrelated things behind one word, which is
the mess the split was meant to end.

### Dependencies are given, never resolved as a fallback

**Chosen.** The engines take their harness or client as a required
argument. The runner activity and the script pick them with `harness_for`
and `client_for`; the summary repair the engine calls is also handed in,
with its client made only when a repair is needed. Tests pass fakes.

**Rejected.** `harness = harness or harness_for(job.provider)`: an
optional argument with a fallback. It is two code paths where the tests
only ever take one, and it lets the caller forget that the choice of
harness is its job.


- **Monorepo, one uv workspace, three layers.** `app/` owns the domain
  and knows nothing about Temporal; `runners/` owns the engine binding;
  `common/` holds what two apps share. Imports point down only. A
  placeholder `runners/argo_agentic_factory` README exists to keep the
  split honest.
- **No hardcoded knobs.** Every tunable (a size, limit, timeout, default)
  lives in `settings.toml` with a typed field and a one-line comment;
  facts of a protocol (an env var name, a header, a prompt) stay as named
  constants beside their one user. A test asserts every knob is a setting.
- **One file, one job; empty `__init__.py`; no `utils.py`.** From the
  knowledge-base recipe `coding/structure`, applied to every package.
- **Folders by subject, not by kind.** `job/` groups its files as
  `coders/` (the harness base, the catalog and one folder per coder),
  `process/` (spawning, environment, workdir, output tail), `summary/`
  (the coder's own summary: shape, prompt, block, parse, repair) and
  `report/` (the conversation and the step that judges it); `step/` has
  `providers/`; the runner keeps what only activities use under
  `activities/`. A prefix shared by siblings (`summary_*.py`) is the sign
  a folder is due. Rejected: `models/`, `utils/`, `helpers/` folders that
  group by kind and put one subject in three places.
- **Harness calls preferred over API calls for cost**; both are activities.
  Jobs ride the coder subscriptions; steps ride the same subscription
  through the Go API.
- **Built with a coder fleet.** The store, journal, conversation, report
  and runner changes were implemented as fleet tasks (opencode with
  muse-spark, worktree isolation, one spec file per task, dependencies
  declared at creation), reviewed line by line against the spec and
  checked with ruff, mypy strict and pytest before each push.
