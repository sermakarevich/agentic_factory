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
  harness closes the run from `end_of_stream()`, without totals.
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

### Callbacks: three hooks, not return values

- **Chosen.** The engine takes one `Callback`, a base class with three
  no-op methods: `on_start(job)` after the session is known and before
  the coder starts, `on_event(event)` per event, `on_end(JobEnd)` once on
  every ending (result, `JobFailed`, cancellation) with the result or the
  failure text and the ledger's totals so far. The engine does not know
  who listens. The runner fans out to a heartbeat callback (Temporal
  liveness plus the context size of the last turn), a log callback and a
  journal callback (the store).
- **Why.** The engine stays engine-agnostic and testable with no Temporal
  and no database. Adding Langfuse later is one more callback on the same
  stream.
- **Why start and end, not just events.** The try's row needs opening
  before the coder runs and closing with its totals whatever way the run
  ended; done from the activity, that was domain logic (what a try is,
  what it adds up to) in the runner. As callback hooks the journal owns
  the whole try and the activity only wires. A base class, not a
  Protocol, so a callback overrides the hooks it cares about.
- **The `job` row is summed in the app.** `job/record.py` reads the
  session's tries from the store and writes one row; the runner's
  `record_job` activity is one line that hands it the store. The
  aggregation is domain logic, so it lives beside the engine and is unit
  tested there; the activity keeps only Temporal's concerns (timeout,
  retries, not fatal).
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
  `event`, `conversation`, `report`, `job`. The `event` row holds the whole
  `Event` as json (raw line included) with the try number and the coder's
  timestamp. Written live by a `JournalCallback`, which also opens and
  closes the `attempt` row. Totals (tokens, cost, duration, turns, tool
  calls and failures) are flat columns on `attempt` and `job`, the same on
  both, so sql can sum and compare them without unpacking json.
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
- **Where it lives.** `common/` because both the app (journal callback)
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
  facts, run with a plain `Callback()` so its tokens do not pollute the
  heartbeat's context reading.

### Structured output of a job: asked in the prompt, picked out by a step

- **Chosen.** A workflow that needs typed data out of a job gives its JSON
  schema. The prompt gets a request to state each field plainly in the
  final message, before the summary block. After the job, one step with
  the schema wrapped as "the output or null, plus the fields not stated"
  reads the coder's last message; when it says not stated, a second step
  reads the whole rendered conversation. Not stated there either is
  `StructuredOutputNotStated`, a final failure: the workflow stops, as
  fleet's did on a missing outputs file. `job/structured_output/` in the
  app (contract, prompt, step, extract), `StructuredOutputActivity` and
  `run_job_with_structured_output` in the runner. The output is saved in
  its own `structured_output` row with the schema and which pass found it;
  the job engine is untouched.
- **Why "structured output", not "outputs".** A job has many outputs
  (files, events, the report); the name says which one this is: the
  schema-shaped answer, the same thing a step returns, here stated by a
  coder and picked out by a step.
- **Why a step over the stored events.** The events are already stored
  and the step engine already exists; the output is a lookup in the
  text, not an inference, once the prompt asked for it. The null branch
  in the schema is what keeps strict mode from forcing invented values.
- **Rejected: an outputs file in the workdir** (fleet). Ties the job to a
  filesystem the workflow must reach and to a path convention; a job with
  no workdir of its own has nowhere to write.
- **Rejected: a tool or a store write by the coder.** An MCP tool or a
  `set_outputs` command the coder calls puts a write path into the coder's
  hands and needs per-coder tool plumbing; the coder's words are enough.
- **Rejected: a second JSON-block parser** next to the summary's. One
  fenced block per message is what coders manage; a second one competes
  with it, and the summary parser already carries five layers of repair.

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
  the same callbacks, so a step and a job look alike to whoever listens.
- **Provider.** The OpenCode Go API, covered by the same subscription as
  the opencode CLI, through the `openai` SDK. The protocol is picked from
  the model name: chat completions by default, Responses for muse-spark,
  grok and gpt. Learned by probes: the SDK works once the user agent is
  overridden, each request needs a fresh `x-opencode-session` header,
  reasoning models spend most output tokens thinking so `max_tokens` must
  leave room, and a reasoning effort of `low` cut glm-5.3-flash from 30 s
  to 6 s. No retries in the client: Temporal retries.
- **Where steps are used.** Repairing a coder's summary block, the report
  over a session, the structured output picked out of a job's text, and,
  planned, any typed judgement between two jobs.
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
  `build_report`, `record_job`. Retries never appear in workflow code;
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
- **Search attributes for the UI, memo rejected** (Sep 30). The workflow
  list showed status, id, type and times, nothing about the job. Six
  Keyword search attributes (`Provider`, `Model`, `Workdir`, `Runner`,
  `Outcome`, `Verdict`) now travel with the workflow: set at start by the
  cli, upserted by the workflow as it learns them. A memo would have been
  simpler (no registration) but the UI shows a memo only on the workflow's
  own page, not as list columns or filters. The runner's identity became
  `host:pid:sha` instead of the SDK's `pid@host`, so the `Runner` column and
  the workers page say which checkout is running. The workflow cannot ask
  the server which worker ran an activity, so the job activity returns
  `TryResult(result, runner)` and a failed try's `ActivityError` carries
  the identity. Registration is a cli command (`factory attributes`, list
  then add the missing) rather than `start-dev --search-attribute` flags,
  so the names live in one module; the time-skipping test server takes the
  add call but has no list, which is why the tests call `add` directly.
- **Proven by the restart test.** Runner killed mid-job and restarted:
  Temporal failed the try with a heartbeat timeout, try 2 started with
  attempt 2 in the session made before try 1, and the coder resumed it
  saying it would not redo the work. Found: killing the runner did not
  kill the coder, which kept working as an orphan; the process group fix
  is in (below), the watchdog for a hard death is in TODO.
- **Activities are classes with the store given** (Sep 30). The first cut
  had a module-level `store.py` making a `Store` on import and activities
  as free functions reading it, so tests monkeypatched a global and the
  engine was never disposed. Now `runner.py` makes one `Store`, gives it
  to `SessionActivity(store)`, `JobActivity(store)`, `ReportActivity(store)`,
  `RecordActivity(store)` and disposes it in `finally`; workflows call
  them with `execute_activity_method`. The rule "dependencies are given,
  never resolved" applied to the runner.
- **Domain logic left the activities** (Sep 30). The session activity
  had the default model, the session creation and the store write in its
  body; the report activity had load, render, save, report, save. Both
  moved to the app (`job/session.py: start_session`,
  `job/report/build.py: build_report`); an activity now adds only the
  Temporal parts (heartbeat, `activity.info()`, the error mapping).
- **Retryable is a property of the failure** (Sep 30). `JobFailed` has
  `retryable = True`; `CoderNotFound` and `SessionNotCreated` set it
  false and the runner maps that to `ApplicationError(non_retryable=True)`.
  Before, every failure was retried up to `max_attempts`, including a
  missing binary, which is five identical tries for nothing.
- **What ends a try is named in the outcome** (Sep 30). `_failure_text`
  handled only `ApplicationError`; a heartbeat timeout came out as
  `ActivityError: ...`. It now names the Temporal timeout kind
  (`Timeout: heartbeat`, `Timeout: start to close`) and a cancellation.
- **Step activity dropped** (Sep 30). `execute_step` had no workflow
  calling it and its timeout was shorter than the app's step timeout. The
  report activity's timeout is now the app's `step.timeout_sec` plus a
  margin, read from the app's settings, so the two cannot drift apart.
- **The transcript opens with the request** (Sep 30). The report step
  judged `unknown` on a live job: "the original user request is not
  shown in the transcript". The prompt was only in the `session` row
  and the conversation was rendered from events alone. `build_report`
  now loads the session (`Store.load_session`) and `render(prompt, rows)`
  puts a `user:` block first. Emitting the prompt as an event instead was
  rejected: it is not something the coder said, and the row already holds it.
- **Usage is unknown, not zero, when the coder never said it** (Sep 30).
  The same job reported 0 tokens and $0: opencode dropped its last
  `step_finish`, the harness synthesized `finished` from totals it never
  got, and the ledger took those zeros as the coder's own. `finished` now
  carries no usage in that case, the ledger keeps the sum of the turns it
  saw, and `JobResult.usage_known` says whether the totals are the
  coder's.
- **Usage is read back from opencode after a lost last line** (Sep 30).
  The loss is not a rare race: opencode's run client exits on the
  session going idle before it drains the final `step-finish`, so the
  last turn's tokens are lost on nearly every run. opencode keeps every
  message with its tokens and cost, so after a run whose `finished` has
  no usage the engine asks `session.message.list` and sums the assistant
  messages created since the try began. The harness gives the command
  and the parser (`usage_command`, `parse_usage`); `job/usage.py` runs it
  under `usage_wait_sec` and gives up quietly on any failure, so the
  result never waits on or fails for the accounting. Reading opencode's
  store through its own API is fine; writing into it is not. The time
  fence is the try's start, not the session's: a retried job shares
  the session and must not count the earlier tries twice. The totals
  travel as a `usage` event through the same callback as the stream,
  not as a fix-up of the ledger alone: the journal is the record the
  reviewer reads, and it should say what the stream said and what was
  found afterwards, in that order.
- **Workflows are Python, not YAML.** Graphs are code; a data-driven DAG
  interpreter can be added later if needed. Beads is an input source and
  an output target, not the internal state store.
- **Distill: the app's steps, the runner's order** (Sep 30). Fleet's
  distill flow was a YAML graph over 1,900 lines of tools (sources,
  chunking, verify, topics) and prompt files. The tools and prompts moved
  as they were into `app/distill`; the graph became
  `distill/workflow.py` in the runner, with the fetch and the verifier
  as activities and every other step a job. Rejected: a distill
  package inside `agentic_factory` (a second domain in the first app's
  tree), and workflow code in the app (it is written against the
  Temporal API, so it belongs to the runner). The fetch activity's
  timeout is 300 s, not fleet's 900 s tool ceiling: the app's own
  limits are 60 s per http call and 180 s per cli call, with two
  retries.
- **The app is called `distill`, not `summarise`** (Oct 1). A summary is
  one of the eight files a run writes; the name undersold the output.
  `distill` says what the run does to a source: boils it down to its
  substance, as a folder in the knowledge base. Considered:
  `knowledge_entry` (names the output exactly but is long and dull),
  `dossier` (exact but unusual in code), `study` (vague), `ingest`
  (reads as loading into a database, which never happens).
- **A job that must succeed raises** (Sep 30). Chained workflows kept
  writing `if outcome.result is None: raise ApplicationError(...)` after
  `run_job_with_report`. That became `run_job_or_fail` in
  `job/workflow.py`; the structured-output helper and every distill
  job use it.
- **The research run has no human gate yet** (Oct 1). Fleet's research
  flow stopped at the shortlist for a person to approve it. The runner's
  research workflow skips that stop: the plan goes straight from the
  assign job to the source runs, and the shortlist is what the judge and
  the assign job say. The gate comes back as a signal when wanted, not
  as a second workflow.
- **One child distill workflow per fresh source, failing softly** (Oct 1).
  One dead source must not sink the run: a child run that failed becomes
  a `skipped` ledger row with its reason, and the digests read only what
  was filed. At most `sources_at_once` children run together, since each
  one spends several coder slots.
- **Planning jobs run on a stronger model than writing jobs** (Oct 1).
  Discover searches the web and assign reads the ranked rows; both run
  on the planning coder and model with the longer planning timeout. The
  writing jobs (topic digests, aggregates, lenses, index) ride the
  subscription coder the distill jobs use.
- **The global job cap counts coder workflows only and is a soft gate**
  (Oct 1; superseded the same day by per-provider coder queues, below). `[limits] max_concurrent_jobs` bounds the running `job` and
  `job_with_structured_output` workflows on the queue, the types that run
  a coder themselves; the names come from the classes' `@workflow.defn`.
  The first cut also counted `distill` and `research`, but they only
  orchestrate: their coder work runs as those child workflows, so one
  research run counted several times over and a cap of 4 blocked every
  submit and froze the poller. Every spawner asks `capacity.free_slots`
  (None when the cap is 0): `af run`, `af distill` and `af research`
  refuse at 0 unless `--force`, the poller spawns at most that many per
  tick within `batch_limit`. It is an admission check, not a lock:
  visibility counts lag by a second or so and two submits at once can
  both pass. The hard per-machine limit stays `[runner]
  max_concurrent_activities`.
- **Jobs are child workflows** (Oct 1). `run_job_with_report`,
  `run_job_or_fail` and `run_job_with_structured_output` start the job
  workflow as a child with id `<parent id>/<job name>`, the name as summary,
  its search attributes at start and REQUEST_CANCEL, instead of running the
  job's activities inline. Inline, a job had no row of its own in the UI and
  its `after_job` upserts overwrote the parent's attributes job after job.
  A `ChildWorkflowError` is mapped as the inline failure was: `JobFailed`
  on the fatal path, a failed `JobOutcome` on the soft one. The workflows'
  bodies stay usable inline (`run_job_here`) for the child itself.
- **Workflow ids come from names, plus a `Name` search attribute** (Oct 1).
  `job-<slug>-<4 hex>`, `distill-<url tail>-<4 hex>`,
  `research-<topic>-<target>-<4 hex>` from one function in `cli/ids.py`,
  so a list of runs reads without opening them; `Name` is set at start on
  every workflow, children included, and `af list` shows it.
- **Coder limits are per-provider queues served by one coders process**
  (Oct 1). `execute_job` goes to `<task_queue>-coder-<provider>`; `af coders`
  runs one worker per `[providers.<name>]` table with
  `max_concurrent_activities = max_concurrent` (claude 1, opencode 5), and
  refuses to start twice. This replaces the soft global cap
  (`capacity.py`, `cli/admission.py`, `--force`, `[limits]`, the beads
  free-slot check): a Temporal limit holds per worker, so one process per
  machine makes the limits exact, where visibility counts lagged and let
  two submits through. Workflows start freely and wait in the queue; the
  execute activity has no schedule-to-start timeout. `af runner` keeps the
  workflows and the quick activities.

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

### Settings: one loader, shared values in `common/factory_settings`

**Chosen** (Sep 30). The dynaconf-to-pydantic loader lives once in
`factory_settings.load`, every settings model is a `Table` with
`extra="forbid"`, and values more than one package needs (the store's url)
live in `factory_settings.shared`. Env override is `AF_<TABLE>__<KEY>` for
every package; migrations and the runner read the same `shared.store.url`.

**Rejected.** Each package with its own copy of the loader (the app and
the runner had two identical ones) and the store's url as an app setting
that the migrations then read from a differently named variable
(`FACTORY_STORE_URL`). Two places to change one thing.

**Why `extra="forbid"`.** A misspelled key in a toml file or an `AF_`
variable used to be dropped in silence; now the load refuses it. The
loader keeps only the dict-valued keys of dynaconf's output, because
dynaconf adds its own flat keys (`LOAD_DOTENV`) that the models must not see.

### Callbacks: `on_event` for everyone, the lifecycle for jobs

**Chosen** (Sep 30). `Callback` has only `on_event`, and a step and a job
give their events to it alike. `JobCallback` adds `on_start` and `on_end`;
the job engine calls `on_end` on a result, on any error and on
cancellation, from `finally`, and the fanout runs every callback and
raises the first error after. The kill path signals the coder's process
group, so opencode's private server dies with it.

**Rejected.** A `Silent` callback (a base with no-op methods is already
silent) and `LogCallback(as_json=True)`: one JSON line on stderr behind a
timestamp prefix. Machine output is `JsonLinesCallback` on stdout, with
no prefix, and the human log stays on stderr.

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
- **Apps do not import from apps** (Sep 30). `app/distill` was first
  sketched depending on `agentic_factory` for its `Job` contract. It
  does not: an app is one domain, its steps are prompts and plain
  functions, and the runner is the only place that knows both the
  domain and the job engine. What two apps would share moves to
  `common/`. Workflow-specific Temporal artifacts (the workflow, its
  activities, its settings table, its cli command) live in the runner,
  next to the workflow they serve, not in the app they order.
- **A distill request may name its folder** (Oct 1). Fleet's summarise
  flow had no target folder: `topic` files the entry under a research
  topic and `research_target` is a provenance line only. Distill keeps
  both and adds `target_dir`: the plan job writes the entry into that
  folder as is, with only the same-source and foreign-entry checks. A
  target dir and a topic are refused together. The research workflow,
  which picks one folder for many sources, will pass it to each child.
- **The judge is a second kind of step, not a provider of the llm step**
  (Oct 1). A judgment has no prompt and no output schema: it is named
  typed questions over one state, answered with probabilities, by a model
  that cannot write text and bills differently. Forcing that into `Step`
  would mean a prompt nobody reads and a schema the provider ignores. So
  `step/judge/` has its own contract, client base, catalog and engine,
  and shares the failure family, the event stream and the activity
  pattern with the llm step. First client: TypeSafe jev.
- **Jobs have names, and the UI reads them** (Oct 1). A distill run showed
  64 activities under 7 names, nine `execute_job` bars at once with
  nothing saying which chunk each was. `Job.name` (`wiki/3`, `digest`) is
  the label: the runner passes it as the summary of each of the job's
  activities, puts it in front of a `JobFailed` message, and the distill
  workflow keeps a status line with `set_current_details`. Summaries and
  details are metadata, not history, so they change no replay. Child
  workflows per job, the bigger restructuring of the timeline, wait for
  the research workflow.
- **The runner is grouped by subject, not by Temporal kind** (Oct 1).
  `activities/distill.py` and `workflows/distill.py` were one subject
  in two folders, which the structure rules forbid (group by subject,
  never by kind). Now one folder per workflow holds its workflow,
  activities and cli command, with the two modules every subject's
  activities use (`failure`, `heartbeat`) at the package root; the
  settings file stays one, tables ordered by subject. Superseded by the
  next bullet.
- **The runner is grouped by role, then by subject inside each role** (Oct 1).
  Top-level folders are `workflows/` (one folder per workflow with its
  activities), `watchers/` (things that watch a state and start workflows,
  the DESIGN word; today beads), `cli/` (the `af` command, one module per
  subject: `job.py`, `distill.py`, `research.py`, `beads.py`) and
  `settings/`. The subject folders had grown to mix a workflow, its
  activities, its cli command and, for beads, a poller, so the root read as
  a flat list of unlike things and the cli was spread over five folders.
  Shared code goes to the nearest common ancestor: `failure` to
  `workflows/` (only activities use it), `heartbeat` to `workflows/job/`
  (only the job activity), `options` to `cli/`; `capacity`, used by the
  cli and the beads watcher, stayed at the root with `runner`, `client`
  and `identity` (removed later that day with the global cap). Imports point from cli to watchers to workflows, never
  back. A pure move: every workflow, activity and search attribute name,
  the settings tables and the beads schedule id are unchanged, so running
  workflows and the schedule survive a runner restart.
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
  `providers/`; the runner groups by role (`workflows/`, `watchers/`,
  `cli/`, `settings/`), then by subject inside each role. A prefix shared by siblings (`summary_*.py`) is the sign
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
- **Distill: prompts as one API over flat templates,
sources one module per kind** (Oct 1).
  Ten prompt folders (each an `__init__.py`, a `prompt.py` building a dict
  by hand, a `.md`) became `prompts/__init__.py`: one `Entry` plus
  `plan/page/wiki/index_prompt` over flat `*.md` files, the repo variant
  picked by file existence. A 914-line `sources.py` became `sources/`
  with one module per kind behind one `{SourceKind: fetcher}` table; the
  workflow's stages became data (`READER_STAGES`) with one `_written`
  helper whose status line counts jobs in as they finish.
- **Rejected.** Keeping the ported fleet layout: ten near-identical prompt
  dicts, a route table of lambdas, one function per workflow stage.
- **Why.** Prompts are read as prose far more often than code; code only
  chooses and fills. Proven byte-identical: every prompt rendered for a
  text and a repo source before and after, pinned by `tests/test_prompts.py`.
- **Distill prompt text lives in .md files, Python only chooses and fills** (Oct 1).
  Prompts are read and edited far more often than code; a text file diffs
  and reviews as prose, with no escaping for braces or quotes. Python keeps
  only the choice of template, the optional section, and the variables.
  The one renderer is `string.Template`, strict: a missing variable raises.
- **Two runner processes on one machine, not one bigger one** (Oct 1).
  One runner meant every code change killed every job in flight on
  restart, and a crash stopped the whole factory. `just runners N`
  starts N processes polling the same queue; each has its own identity
  in the UI and its own log, and one can be restarted while the other
  keeps its jobs. Concurrency is still `[runner]
  max_concurrent_activities` per process, so N runners run N times as
  many coder jobs at once; lower the setting if the machine is
  loaded.
- **The vault paths are shared settings in `common/factory_settings`** (Oct 1).
  A second app needs the same knowledge-base folders and apps never import
  each other, so the `[vault]` table and its readers moved down a layer.
  Distill keeps what is its own: `[entry].pdf_copy_max_bytes` for the plan
  prompt and `[fetch].work_root` for the run work folder.
- **The prompt renderer is two lines of stdlib inlined in each app's
  prompt module** (Oct 1). `distill`'s `rendered(folder, name, values)`
  was shared with `research` through a common package; that package is
  dropped and each app's prompt module holds its own two-line
  `_rendered` (`read_text` plus `string.Template(...).substitute`),
  strict on missing variables. Below a few lines of stdlib glue two
  copies beat a package (pyproject, justfile, tests, lock entry, a
  check step).
- **Research ranks with the judge step, not with a chat model** (Oct 1).
  Scoring is three jev questions asked verbatim over each candidate's
  metadata (relevance, kind, authority): calibrated, cheap, and the three
  questions are facts of the flow, kept as named constants beside their
  one user in `research/rank.py`. A chat model ranking the same list was
  rejected: uncalibrated scores, full-context cost, and wording that
  drifts per run.
- **The discover job states a path, the file holds the candidates** (Oct 1).
  The candidate list is too big for a structured output (tens of rows with
  abstracts), so discover writes `<target>/candidates.json` and states
  only `candidates_path` in its final message. The ranking, the plan and
  the ledger all read the file from there.
- **Research is one state, one candidate, flat prompts** (Oct 1). The first
  port was mechanical: three models for one candidate (scored, ranked, plain),
  two for one planned source, 30 prompt files for 10 jobs, domain logic in a
  450-line workflow. Now one `Candidate` carries `status` and `scores` through
  every stage, one `PlannedSource` is linked when it has an `origin`, one
  `Research` state model grows as the workflow goes and answers what the
  prompts ask (`run.py`), and `prompts/prompt.py` fills the flat `.md`
  templates from one `values` function, as distill's does. The judge
  questions are one plain dict in `rank.py`; the runner only converts them to
  `Question` and the answers to plain values, so no question text or level
  arithmetic lives there. `locate` and `candidates` folded into
  `activities.py`. Rejected: one prompt module per job (a function per
  template added nothing but a name).
- **af owns its beads database at ~/.agentic_factory/beads; fleet no longer
  used** (2026-10-01). The watcher shelled out to `fleet ready --json` and
  `fleet bd ...`, so stopping fleet's supervisor stopped the beads intake.
  Now every call is plain `bd` run with `[beads].home` as its cwd
  (`BEADS_DIR` dropped from its environment, so the cwd alone picks the
  database), `af beads init` makes it with the prefix `af`, and
  `af beads add` writes the routing as bd metadata on the bead itself
  (`af_provider`, `af_cwd`, `af_model`). A ready bead needs a configured
  provider and an existing workdir or it stays open with the reason in the
  tick summary. Rejected: a task.json beside each bead (a second source of
  truth that `bd` does not move with the bead) and keeping fleet's
  `coder`/`isolation` row keys (nothing downstream used `isolation`).
- **Superseded by "back to a Schedule" below.** **beads watcher: one
  long-running workflow with continue-as-new instead of a Schedule; keep last
  N runs** (2026-10-01). The `beads-poll` Schedule started
  a one-tick workflow every 10 s, 8,600 runs a day, and made the Temporal UI
  unusable. Now one `beads_watcher` workflow (fixed id `beads-watcher`) runs
  the unchanged tick activity, sleeps `interval_sec` and repeats; a failed
  tick is recorded, not fatal; after `checks_per_run` ticks (or when Temporal
  suggests it) it continues as new. The loop is kept tiny and frozen so it
  replays across code changes: tick logic changes go into the activity, loop
  changes need `af beads restart`. Its knobs travel in the input, not read
  from settings in workflow code, so a settings change cannot break a replay.
  The last tick is a `last_check` query plus a `LastCheck` keyword attribute
  upserted only when its line changes. A best-effort `trim_watcher_runs`
  activity deletes all but the newest `keep_runs` (3) closed `beads_watcher`
  and `beads_poll` runs, by run id, never another type. `af beads
  schedule`/`unschedule` and the in-process poll daemon are gone;
  `af beads start` removes the legacy schedule. Rejected: keeping the
  Schedule with a shorter namespace retention (still thousands of rows and a
  server-wide setting), and an in-process daemon (dies with its terminal).
- **A bead's job parameters are one `af_job` metadata object, with front
  matter under it** (2026-10-01). The flat `af_provider`/`af_cwd`/`af_model`
  keys covered three of Job's fields; now a bead sets any of `provider`,
  `model`, `name`, `workdir`, `tools`, `timeout_sec`, `stall_sec`,
  `context_limit_tokens` and `structured_output` (which picks the
  structured-output workflow), in one JSON object so `bd update --metadata`
  replaces it whole and other metadata keys stay. A `---` front matter block
  at the top of the description gives the same fields for hand-written
  beads; precedence is Job's defaults < front matter < `af_job`. Unknown keys
  and bad values skip the bead with one comment per reason, not one per
  tick. `af beads add` takes `af run`'s job options and `af beads set`
  merges them into a waiting bead. No compatibility for the flat keys: the
  database is a day old. Rejected: one metadata key per field (no way to
  validate unknown keys, and a structured-output schema in a flat value).
- **Chains are bd dependencies; a failed step blocks its bead** (2026-10-01).
  `af beads add --after ID` sets the dependency in the same `bd create`, and
  `bd ready` already holds back dependents of beads that are not closed, so
  af tracks nothing. A bead is closed only when its workflow completed with a
  result and a `done` verdict; anything else blocks it with one
  `[af] blocked: ...` comment, which stops its chain and ends the repeated
  "left in_progress" notes. `af beads retry` comments `[af] retry` and then
  reopens it; the next spawn is `bead-<id>-<n>` with n counted from the
  markers, so a retry never collides with the old run. Rejected: closing on
  COMPLETED alone (a coder that gave up would release its dependents), and
  one workflow per chain (a second copy of what bd already knows).
- **The rest of bd is forwarded, not wrapped** (2026-10-01). `af beads bd
  <args...>` runs bd in the beads home with the arguments untouched and its
  output and exit code passed through; any `af beads <cmd>` af does not
  define falls through to it (a group whose `resolve_command` falls back to
  `bd`). af's own names win, so `af beads bd status` is the way to bd's.
  Rejected: wrapping each bd command (always behind bd), and telling users to
  `cd ~/.agentic_factory/beads && bd ...` (easy to run in the wrong folder).
- **Back to a Schedule for beads, every 30 s, with a cleaner that keeps the
  last run** (2026-10-01). **The trim inside `beads_poll` (`trim_poll_runs`,
  `keep_runs`, `trim_timeout_sec`) is superseded by "the cleaner is its own
  scheduled workflow" below; the rest stands.** Supersedes the long-running watcher above. The
  user prefers one schedule row with a visible next run over a workflow that
  never ends. Schedule `beads-poll` starts a one-tick `beads_poll` run every
  `interval_sec` (30 s), overlap SKIP so a slow tick never stacks; the run
  ticks, trims, and returns the tick's summary as its result. A failed tick
  still trims, then fails the run (a red row, simpler than a failed summary).
  The flood that made us leave the first schedule is solved by the cleaner,
  not by fewer runs: every run deletes all closed `beads_poll` (and leftover
  `beads_watcher`) runs but the newest `keep_runs` (1), never the running one
  and never another type. `af beads start` creates or replaces the schedule
  and terminates the old `beads-watcher` workflow; deploying needs it once.
  Removed with the loop: `WatcherRun`, `checks_per_run`, `stop_wait_sec`,
  `query_timeout_sec`, the `last_check` query, `last_check.py`, `legacy.py`
  and the `LastCheck` attribute (dropped from the registered keys too: a
  server that has it keeps it unused, which breaks nothing). Rejected: keeping
  the loop (no next-run in the UI) and a 10 s schedule without the cleaner
  (the old flood).
- **The cleaner is its own scheduled workflow with per-type rules**
  (2026-10-01). Supersedes the trim inside `beads_poll` from the entry above.
  A Schedule `cleaner` starts a `cleaner` run every 60 s (overlap SKIP); its
  one activity applies `[[cleaner.rules]]`, one rule per workflow type with
  `keep_completed` and `keep_failed`, and returns per type how many completed
  and failed runs it deleted and how many calls failed. Completed is
  Completed or ContinuedAsNew, failed every other closed status, so a few red
  rows stay to read; running runs are never touched. The `cleaner` type has a
  rule of its own, so it cleans itself. Only the rule's type is touched: the
  type name is validated as a plain name before it enters the query, and
  each listed row's type is checked again. The rules travel in the
  schedule's input (a settings change takes `af cleaner restart`), and
  `af cleaner run` does one clean in the calling process. The schedule code
  both schedules need (build, create-or-replace, delete tolerating
  NOT_FOUND, describe with the last run's line) moved to one `schedules.py`.
  `beads_poll` is just the tick now: `trim.py`, `trim_poll_runs`, `keep_runs`
  and `trim_timeout_sec` are gone (an old schedule's input with
  `trim_timeout_sec` still decodes, the extra field is ignored). Rejected:
  keeping the trim in each watched workflow (every new scheduled type would
  repeat it, and the poll's run would fail for a cleanup reason), one keep
  count for all closed runs (a failed tick would be deleted by the next good
  one before anyone reads it), and cleaning every type (jobs' history is
  worth its 24 h retention).
- **Tutorials are their own app and workflow** (2026-10-01). `af tutorial
  "<topic>"` writes `knowledge/tutorials/<name>/` through the `tutorial`
  app and workflow. The designer is one structured-output job that writes
  its plan and one spec per chapter to disk (`plan.md`, `specs/NN_<slug>.md`)
  and states the plan, which the workflow checks before any writer starts:
  the specs on disk are what writers and reviewers read, so the prompts stay
  short and a run can be read afterwards. Chapters fan out, one writer job
  each, all at once; each is reviewed by a structured-output job, and a
  failing chapter gets at most `review_rounds` (2) rewrites, then is marked
  failed while the others finish. A shared `project/` is scaffolded by the
  designer; a writer only adds files named for its chapter. One finish job
  does the consistency pass and the indexes. No approval gate and no git
  commit. Rejected: one job writing the whole tutorial (too long for one
  context, nothing to review per chapter), an unbounded review loop (cost
  with no end), and failing the run on one bad chapter (the rest is worth
  keeping).
