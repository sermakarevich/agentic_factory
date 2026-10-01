# agentic_factory — design

Temporal-based orchestration for AI-agent work. Successor to `fleet`.
Temporal owns state, retries, schedules and history. We own the runner
that drives coder CLIs, the abstractions below, and the artifacts.

## Atomic abstractions

| # | Name | Meaning | Temporal shape |
|---|------|---------|----------------|
| 0 | **step** | one structured-output request to a model (needs an API key); its second kind, the **judge step**, asks typed questions over a state and gets probabilities back | short activity |
| 1 | **job** | one headless harness run (`claude -p`, `codex`, `opencode`); cheap tokens via subscription | long activity with heartbeats |
| 2 | **workflow** | jobs and steps composed: a job, a step that shapes its output, another job; Python around them (worktree, bead status); static or dynamic fan-out | workflow made of activities |
| 4 | **watcher** | monitors a state (beads, X) and starts workflows | long-running workflow with a timer loop; deterministic run ids |
| 5 | **schedule** | starts a workflow on cron | Temporal Schedule |
| 6 | **manual trigger** | starts a workflow from the CLI | CLI over the Temporal client |
| 7 | **hil** | human in the loop: escalate and ask (`ask_human`) | blocking tool + heartbeats inside a job; signal at workflow level |
| 8 | **artifacts** | deliverables plus a report explaining the work | activity return value + artifact store |

Vocabulary rules:
- The process that polls Temporal task queues is the **runner**, never
  "worker". "Worker" is not a concept here any more (decision Sep 2026, below).
- **run** = one execution of a workflow. **try** = one attempt of an
  activity. The word "task" is avoided (beads task, Temporal task and
  fleet task all differ).

## Use case

Execute any AI-agentic run: coding, automation, data collection,
document processing, communication. Started manually, by a bead, by a
watcher, or by a schedule.

## Needs and how they are met

1. **Worker crash → continuation.** Every try of a job runs in one
   session, made by an activity before the first try. The job activity
   gets its attempt number from Temporal and the session's last context
   size from the last heartbeat. The prompt opens with a continuation
   header. Completed setup activities are not redone.
2. **Workflow crash → skip finished steps.** Native: completed
   activities and child workflows replay from history. The broken step
   retries as in (1).
3. **Hangs with cause-aware restart.** The runner parses the harness
   stream and raises one typed error per cause:
   - `RateLimited(resets_at)` → sleep until reset, retry
   - `ContextPressure` → kill at token threshold, retry with the report
   - `ProviderError` / `NetworkError` → backoff retry
   - `Stalled` (no output for N min) → kill, retry
   - `Blocked` (coder asked for a human) → non-retryable, wait for signal
   - unknown → bounded generic retry, then escalate via hil
4. **Observability.** Every event of every try is a row in the store
   (Postgres), the session's conversation is built from them when the job
   ends, and a report step reads that conversation and writes a structured
   verdict. Temporal UI shows graph, timing, retries. Langfuse (fed by the
   same stream) is planned for turns, tool calls and tokens.

## llm job contract

Lives in `agentic_factory/tokens.py`, `event.py`, `failure.py` (shared with calls) and `job/` (contract, coders, and the loop that runs one). Engine-agnostic.

- `Job` — what to run: provider (the harness: claude, opencode), model, `name` (what the job is
  for, in a word or two; labels its activities in the UI and its failure), prompt, workdir, tools,
  timeout_sec, stall_sec, context_limit_tokens, `session_id` (session of an earlier try)
  and `session_tokens` (its last known context size).
  Built by a job definition, sent to the activity.
- `JobResult` — what the run produced: session_id, tokens, cost_usd, usage_known,
  duration_sec, plus `stats` (turns, tool_calls, tool_failures), the coder's
  `summary` (its own account of the job, see "Job outcome") and
  `summary_text` (the block as written, for repair). Built by the engine from
  the `finished` event, the ledger it kept over the stream and its own clock.
  Whether the work is done is not decided here: the summary is a claim and
  the stats are evidence; the workflow judges.
- `Tokens` — input, output, cache_read, cache_write. Per turn in events,
  total in the result.
- `Event` — one normalized message of the coder's stream, named after
  LangChain messages: kind (session, ai, tool, rate_limit, finished,
  compaction, unknown), at,
  session_id, content, tool_calls (id, name, args), tool_call_id, name, error
  (on tool: the call failed), usage
  (tokens of the turn, totals on finished), cost_usd, resets_at, raw (the
  original line). One `ai` event per model turn, then one `tool` event per
  tool output. A line the harness has no rule for becomes `unknown` with
  the text as content, so a changed stream can be debugged from the log.
  A run that ends without `finished` means the coder died.
- `Harness` (`job/coders/harness.py`) — abstract base, one subclass per coder, one instance per run: `command(job)` builds
  the command line, `parse_line(text)` turns one stdout line into events and
  raises a failure when the coder cannot continue, `end_of_stream()` is called once
  stdout closes and returns whatever the stream left unsaid (default
  nothing), `compact_command(session_id)` asks the coder to summarize the
  session and `compacts_while_running` says whether that may happen beside a
  live run. `new_session_command(workdir)` creates an empty session and
  `parse_session(stdout)` reads its id; an empty command means the coder
  takes an id we choose. All sync: pure translation, no process is started
  here. The engine and callbacks are async. Each harness names its `default_model`. Implemented: opencode,
  claude.
- `Callback` (`callback.py`) — a base with one no-op method, `on_event(event)`,
  shared by steps and jobs. `JobCallback` (`job/callback.py`) adds the job's
  lifecycle: `on_start(job)` once the session is known and before the coder
  starts, `on_end(JobEnd)` once, on a result, a `JobFailed` and a
  cancellation alike. `JobEnd` carries the result or the failure text
  (`Kind: message`, or `cancelled`) and what the ledger counted so far:
  tokens, cost, duration, stats. The runner fans out to a heartbeat, a log
  and a journal callback; the engine does not know who listens.
- Failures — `JobFailed` subclasses, one per retry rule: `RateLimited
  (resets_at)`, `ContextPressure`, `Stalled`, `TimedOut`, `ProviderError`,
  `NetworkError`, `CoderCrashed(exit_code, stderr)`. Raised only when no
  result exists.
- `run(job, callback, harness, repair) -> JobResult` in `job/engine.py` — the single entry point.
  Takes the harness the caller picked (`job/coders/catalog.py`), fills the default model, starts the
  process in workdir (both as cwd and as `PWD` in the environment), feeds
  every event to the callback, kills the process on stall, timeout,
  context over limit, a harness failure or cancellation. Exit without a
  `finished` event or with a non-zero code is `CoderCrashed`.

Coder quirks learned from smoke runs (opencode v2.0.12):
- `opencode run` needs `--standalone`, else the last `step_finish` line
  never arrives. Even with it the final line is nearly always lost (7 of
  7 runs on Sep 30, with stdout a file too): the run client exits on the
  session going idle before it has drained the last `step-finish` part
  (upstream issues #26855, #31435, #31365). So the harness finishes the
  run in `end_of_stream()`, and `finished` then has no usage. The engine
  reads the try's usage back from opencode's own record of the session
  (`job/usage.py`: `opencode api --standalone session.message.list`, the
  assistant messages created since the try began, summed; reasoning
  tokens left out as the stream leaves them out). When that read-back
  fails too, the result keeps the sum of the turns the stream carried
  (zero for a one-turn answer) and `JobResult.usage_known` is false: a 0
  there is "not known", never "free". Seen live on Sep 30 (`job-ef580a12`).
- opencode takes its working directory from `$PWD`, not from the real
  cwd. The engine sets both.
- The first standalone start can take ~45 s (plugins and MCP servers
  connect). `stall_sec` must stay above that.
- There is no tool allow-list flag, so `Job.tools` is not enforced there.
- Resume works: `--session <id>` continues the earlier session and the
  `finished` event carries the same session id.

Coder quirks learned from smoke runs (claude 2.1.x):
- `--allowedTools` is variadic and swallows what follows, so the prompt
  goes right after `-p`.
- claude waits on an open stdin, so the engine starts every coder with
  stdin closed.
- Without a tool list the run uses `--dangerously-skip-permissions`, as a
  headless run has nobody to answer a prompt. With a list only those tools
  are allowed and the rest is denied.
- `rate_limit_event` is emitted on every run once usage passes a warning
  threshold; only status `rejected` is a failure.
- `result` carries the totals and `total_cost_usd` computed by claude, so
  nothing is summed in the harness; a stream without `result` is a crash.

## Continuation

The session is chosen before the first try, so every try starts the coder
the same way: `--session <id>` (opencode) or the session flags of claude.
Nothing on our side decides between "resume" and "start over"; the coder's
session holds whatever the earlier try did, possibly nothing.

`job/usage.py`: `recover_usage(harness, job, since)` is the read-back
above, for any coder whose `usage_command` is not empty. Best effort and
bounded by `job.usage_wait_sec`: a failure, a timeout or an answer that
is not the record leaves the usage unknown; the result does not depend
on it. It runs only for a run that reached a result; a crashed or killed
try reports the sum it saw. What it finds becomes a `usage` event, sent
to the callback after `finished` and added to the ledger like any other
event, so the journal and the transcript carry the totals too: the
transcript reads `finished: no usage` and then `usage read back from
the coder: in=... out=...`.

`job/session.py`: `create_session(job)` makes that session. For a coder that
takes any id we choose (claude: `new_session_command` is empty) it is a
uuid. For opencode it runs `opencode api --standalone session.create` in
the workdir and reads the id from the answer (sessions are scoped by
project, so the workdir matters; errors come back as JSON with exit 0, so
the answer is validated). The job engine calls it when a job arrives without
a session, for direct runs; a workflow calls it as an activity before try 1,
so that retries share the result.

`job/continuation.py`: `continue_job(job, attempt, session_tokens)` is the
job for try N: the same job and session, the session's last known context
size (so the engine knows whether to compact first), and a header saying
it is a continuation. Try 1 is unchanged. Kept as its own module because
the header is prompt wording the coder sees: app, not runner.

What a retry sends was a choice. The bare prompt again, with nothing about
the retry, was tried on claude: it redid the first step of a killed job and
only afterwards mentioned the earlier attempt. "Continue where you left
off" instead of the prompt reads best to the coder, but needs a probe of
whether the session has any message (a try can die before the coder wrote
one; "continue" in an empty session ends as a false success). claude's
probe is the transcript file the flag choice already uses; opencode's would
be an API call per retry. Chosen: header plus prompt. It needs no probe,
every try on every coder sends the same form, and the header says why the
task appears twice. Whether coders then reliably skip finished work is not
proven: the kill tests' prompt itself said to skip.

Per coder, checked live:

- claude has no single flag: `--session-id <uuid>` starts a session and
  fails with "already in use" on a second run; `--resume <id>` continues one
  and fails with "No conversation found" on a new id; both together are
  refused. The harness picks the flag by whether claude has a transcript
  for the id (`job/coders/claude/store.py`: `<config dir>/projects/*/<id>.jsonl`,
  honouring `CLAUDE_CONFIG_DIR`). A try that died before claude wrote the
  transcript starts the session again, which is right.
- opencode `--session` must name an existing session (`Session not found`
  otherwise, v2.0.12). `session.create` through its API CLI makes one and
  `--session` on it runs and later resumes it with history. Tried and
  rejected: inserting a row with our id into the `session_v2` table of
  `~/.local/share/opencode/opencode.db` also works but writes into a
  private, versioned store whose rows must match the project.

Decision Sep 2026: there is no "worker" in the app. A first cut had a
`worker/` package (definitions with before and after step lists, a state
threaded through Python steps, an in-process chain) mirrored by a Temporal
workflow. It was dropped: the chain was written twice, nothing but a test
called the app's copy, and the Python steps competed with the llm step for
the name. What surrounds a job (workdir, worktree, bead status, tests,
verdict) is written as Temporal workflows composing the two activities, and
any Python that such a workflow needs lives in the app as plain functions
called from an activity.

## Temporal binding

`runners/temporal_agentic_factory`. Activities are one-line wrappers around
the two engines; workflows compose them; retries never appear in workflow code.

- `create_session(job)` — the app's `create_session`, once per job before
  the first try; Temporal keeps the id in history, so a retry of the job
  activity never makes another.
- `execute_job(job)` — reads its attempt number and the previous try's last
  heartbeat (context size) from `activity.info()`, applies `continue_job`,
  runs the job engine with the heartbeat, log and journal callbacks, and
  maps each `JobFailed` to an `ApplicationError` typed by the class name.
  The try's row is the journal callback's: opened on `on_start`, closed
  on `on_end` with the outcome, failure, totals and result.
  `RateLimited` sets `next_retry_delay` to the reset time. Heartbeat details
  are our `Heartbeat` model: time of the last event, event count, context
  size of the last model turn.
- `build_report(request)` — after the job's last try: the app's
  `job/report/build.py` turns the session's prompt and stored events into the conversation,
  saves it, has the report step read it, saves the report and returns it.
  Given the app's step timeout plus a margin, with the `report_activity`
  retries.
- `extract_structured_output(request)` — after a job that must state a
  structured output: the app's `job/structured_output/extract.py` reads
  the session's stored events, runs the extraction step over the coder's
  last message and, when that says "not stated", over the whole
  conversation; saves and returns the output as a dict matching the schema
  in the request. Given two step timeouts plus a margin, with the
  `structured_output_activity` retries. `StructuredOutputNotStated` is
  final: another try would read the same text.
- `fetch_source(request)` and `verify_entry(research_dir)` — the
  `distill` app's fetch and check, each on a thread, behind the
  `fetch_activity` and `verify_activity` timeouts and retries. Free
  functions: neither needs the store.
- Activities are methods of small classes (`SessionActivity`,
  `JobActivity`, `ReportActivity`, `RecordActivity`) that take the store in
  their constructor: `runner.py` makes one `Store` per process, gives it to
  each and disposes it when polling ends. A `JobFailed` whose `retryable`
  is false (`CoderNotFound`, `SessionNotCreated`) becomes a non-retryable
  `ApplicationError`, so Temporal stops the tries at once.
- `record_job(outcome)` — after the report: the app's `job/record.py`
  reads the session's tries, sums them and writes the `job` row. One store
  write behind the `record_activity` timeout and retries; a write that
  failed for good is logged, the workflow still returns the outcome.
- `JobWorkflow` (`workflows/job.py`, type name `job`) — one job, then its
  report; returns a `JobOutcome`. Its `run_job_with_report(job)` helper makes the
  session first when the job has none,
  then carries the activity policy for any workflow
  with a job in it: heartbeat timeout `stall_sec` plus a margin,
  start-to-close `timeout_sec` plus a margin, so the engine kills first and
  Temporal is the backstop, and the retry policy from settings. App code is
  imported inside `imports_passed_through()`, because settings load on
  import and the sandbox would rerun that.
- `JobWithStructuredOutputWorkflow` (`workflows/structured_output.py`,
  type name `job_with_structured_output`) — a job plus the JSON schema of
  the structured output it must state; returns a `JobWithStructuredOutput`:
  the outcome and the output as a dict. Its
  `run_job_with_structured_output(job, schema)` helper is for any workflow
  that needs typed data out of a job: it appends the request to the prompt
  (`job/structured_output/prompt.py`), runs `run_job_with_report`, then the
  extraction activity. A job that failed for good, or an output the coder
  never stated, fail the workflow: nothing downstream can run on made-up
  values. The caller owns the model and validates the dict with it.
- `DistillWorkflow` (`workflows/distill.py`, type name `distill`) —
  see "Distill workflow": the app's steps in order, jobs through
  `run_job_or_fail` and `run_job_with_structured_output`, the fetch and
  verify activities between them.
- Defaults: job fields stay in the app's `settings.toml`, since they describe a
  job whatever engine runs it. The runner has its own `settings/settings.toml`
  for the engine's part: server address, namespace, task queue, activity
  margins, retry policy, concurrency. Precedence for a job field: CLI
  override, then app settings.
- `factory run PROMPT [--workdir] [--provider] [--model] [--timeout-sec]
  [--stall-sec] [--context-limit-tokens] [--tools]` starts one job and
  waits; `just run` at the root. The workdir is made absolute by the CLI and
  created by the job engine. `factory distill URL [--topic]
  [--chunk-chars] [--research-target] [--target-dir]` starts the distill
  workflow and waits. `factory runner` polls.

Learned from the restart test (runner killed mid-job, restarted): Temporal
failed the try with a heartbeat timeout, try 2 started with attempt 2 in
the session made before try 1, and the coder resumed it saying it would not
redo the work. Open item: killing the runner does not kill
the coder process, which kept working as an orphan until it was done. Two
tries of one session can therefore overlap; the engine should make the coder
die with the runner (process group on the same host).

## Context compaction

Two thresholds from `[job]` in settings: `compact_at_tokens` (150k) and
`context_limit_tokens` (200k). Compaction is always on and is not a job
option: the threshold is a setting, not a `Job` field, so no caller can
turn it off or move it. The kill limit stays on
the job, as it is a resource bound like the timeout. The engine computes the
context of every model turn (input plus cache read and write tokens). Above
the first it asks the coder to compact; above the second it kills the run,
`ContextPressure`, and Temporal retries with the session. Each harness says how
it compacts:

- opencode: `compacts_while_running`. The engine runs
  `opencode api --standalone session.compact` in the workdir the first time a
  turn crosses the threshold; opencode applies it at its next step, the run
  goes on, and nothing shows in the stream. Asked again only after the
  context dropped below the threshold and crossed it again.
- claude: cannot be told during a run, so `command` passes
  `--autocompact <compact_at_tokens>` (claude accepts 100k to 1M) and claude
  compacts by itself. `compact_command` is `claude -p /compact --resume <id>`,
  a run of its own (~12 s), used before a resume only.
- On a resume, the engine compacts first when the session's last known
  context (`Job.session_tokens`, from the heartbeat) is at or above the
  threshold. A small session resumes at no extra cost.
- A compaction request is best effort: it is reported as a `compaction`
  event, succeeded or failed, and the run continues either way. The kill
  limit remains the backstop.

## Job outcome

The engine only knows whether the run completed. Whether the work is done is
judged from what the run left behind, in layers from cheap and deterministic
to a model reading text. Lives in `job/stats.py`, `job/summary/contract.py`,
`job/ledger.py`, `job/usage.py`.

1. **Stats.** The ledger counts every event as it flows past: model turns,
   tool calls and failed tool calls (the coders' error flag becomes
   `Event.error`). On `JobResult.stats`. Evidence that costs nothing.
2. **The coder's summary.** The engine wraps every prompt (`wrap_prompt`,
   applied once, in the engine, so every definition and every try gets the
   same wording) with a request to end the final message with a fenced json
   block: task (one sentence), plan (list), execution (list), result (one
   sentence), success (bool). A claim, not a verdict.
3. **Find it.** Detection, not parsing: a partial regexp for the key
   (`job_summary`, quoted or not, then a colon) over every `ai` event, not
   only the last message, since the block may come earlier; the last hit
   wins. The block runs from the object's opening brace to the next fence or
   the end of the message. Fences are ignored on purpose: coders do drop the
   closing one (seen on opencode), and a fence-to-fence regexp then found
   nothing. Our stream, not the coder's session, because a compaction may
   drop the block from the session but never from what we already read.
4. **Parse it in Python.** Several parsers, strictest first: plain json;
   json followed by anything (a fence, prose); a lenient pass for the
   mistakes seen from models (bare key, trailing commas, Python literals,
   text after the closing brace, braces inside strings). Whatever parses
   must still validate as `JobSummary`, with or without the outer key.
   `JobResult.summary` on success; `summary_text` keeps the raw block either
   way.
5. **Repair with a step.** `job/summary/repair.py`: a block that was found but did
   not parse goes to the step engine with the summary schema and a system
   prompt that forbids inventing facts. It runs inside the job engine, right
   before the result is made, with a plain `Callback()`: the step's events stay
   out of the job's stream, since the heartbeat callback would read the
   step's tokens as the coder's context. Any step failure logs and yields
   `summary=None`; the job still succeeds. The schema is sent in strict
   mode, so `JobSummary` forbids extra fields.
6. **The report from the whole session.** After the last try, whatever
   its end, a step reads the rendered conversation of every try (see
   Materialization), which opens with the user's request, and writes a `JobReport`: task, done (with the evidence
   seen), not done, problems, and a verdict `done | partial | failed |
   unknown`. It is told that a claim by the coder is not evidence and a
   command output is. The coder's summary block, when there is one, or the
   last failure text goes in after the transcript. This replaces the
   earlier plan of inferring only the summary from a condensed trace.

Verified Sep 2026: both opencode and claude returned a valid block on a
two-tool job.

Verified on both coders: opencode's queued compaction was applied mid-run in
3 s (19 messages to 4, a structured summary first); claude's `/compact` in
print mode took the context from 22.9k to 2.6k tokens and the next resume
answered from the summary.

## Structured output of a job

A workflow that chains jobs needs typed data out of one job to start the
next (fleet's summarise flow reads the urls one job fetched from a file the
coder wrote). Here the coder writes no file and calls no tool: the workflow
gives a JSON schema, and appends a request to the prompt naming each of its
fields with type and description, to be stated plainly in the final
message, before the summary block the engine asks for. After the job, one
step with a schema built around the workflow's picks the output out of the
coder's last message. The step's schema is the output or null, plus the
fields not stated: strict mode requires every field, and without the null
branch a model that found nothing would fill the output in. The workflow's
schema is made strict the same way (every object requires all its
properties and allows no other), so a hand-written one works like a
pydantic one; an optional field is `anyOf` with null. "Not stated" is an
answer, not a `BadOutput`: it triggers a second step over the whole
rendered conversation. Not stated there either raises
`StructuredOutputNotStated`, final, and the workflow stops. No second
JSON-block parser: extraction is the only path. A found output is saved in
the `structured_output` table with the schema and the pass that found it,
so a later workflow, or a person, can read it without the Temporal
history.

## Distill workflow

The first workflow with a chain of jobs, ported from fleet's summarise
flow: one source (YouTube, X, PDF, arXiv, article, GitHub repo) becomes a
knowledge-base entry (summary, digest, wiki pages, explainer, questions,
critical thinking, index) in the vault at `~/.ai`.

It is split in two places, by the rule that a runner holds no domain
logic:

- `app/distill` is a second application, plain Python with no Temporal
  and no import from `agentic_factory`: the source fetch and chunking
  (`sources.py`, `chunking.py`, `fetch.py`), the check of a finished entry
  (`verify.py`), the topic list (`topics.py`), the vault paths
  (`vault.py`), the contracts the steps exchange (`DistillRequest`,
  `FetchedSource`, `EntryPlan`, `FiledEntry`) and one prompt module per
  job under `prompts/`. Its `settings.toml` holds the vault folders,
  fetch limits (60 s per http call, 180 s per cli call, retry delays,
  throttles per tool), chunk bounds and the verifier's minimum size.
  Every function runs from a test with nothing else up.
- The runner holds what only Temporal needs: `activities/distill.py`
  (`fetch_source`, `verify_entry`: the app's two blocking functions on
  a thread, a `SourceError` mapped to a retryable `ApplicationError`
  only when it says `transient`), `workflows/distill.py`
  (`DistillWorkflow`, type name `distill`) and the `factory
  distill URL [--topic] [--chunk-chars] [--research-target] [--target-dir]`
  command.

The workflow orders the app's steps: fetch (activity, under
`<fetch.work_root>/<workflow id>`), plan (a job with structured output,
validated as `EntryPlan`: the entry folder, slug, title, type), one wiki
job per chunk at once, digest and summary at once, explainer, questions
and critical thinking at once, then the index job followed by the verify
activity; the verifier's problems go back into the next index job's
prompt, up to `distill_workflow.index_attempts` runs, after which the
workflow fails with `EntryNotVerified`. With a topic, a last job moves
the entry under it and states the final path (`FiledEntry`). With a
`target_dir` (CLI `--target-dir`, made absolute) the plan job skips the
routing rules and writes the entry into that folder as is; the request
refuses a target dir together with a topic, since the topic would move the
entry away again. Every job
is built by `distill_job(name, prompt)`: the coder, model and limits of the
runner's `distill_workflow` table, in the vault, named `plan`, `wiki/3`,
`digest`, `index/2` and so on. A job that failed for
good raises through `run_job_or_fail`, so the chain stops where fleet
stopped. The run date the prompts carry is `workflow.now()`, so a replay
sees the same one.

### Reading a run in the UI

A distill run is some 60 activities with 7 activity types, so the names
alone say nothing about which job a bar is. Three things make a run
readable, all Temporal features, none of them history-changing:

- Every activity carries a **summary** (`execute_activity(summary=...)`),
  shown on its bar and in the event list: the job's name for the four
  activities of a job and for the extraction, the source URL for the
  fetch, the entry slug for the verifier, the question names for a judge.
- A job that failed for good fails the workflow as `JobFailed` with the
  name in front: `wiki/3: Stalled: no output for 600 s`.
- The workflow keeps a **status line** (`workflow.set_current_details`)
  on the run page: `wiki pages: 3 of 9 written; running: wiki/4, wiki/5`,
  `index: verifying, attempt 2 of 3`, `done: /path`. It is workflow
  metadata, not history, so it costs nothing on replay.
- The run itself has a **static summary** at start: the source URL of a
  distill run, the job's name of a `factory run --name`.

Child workflows per job (one named row per job in the parent's timeline,
a history a fifth of the size) are the next step and wait for the
research workflow, which needs child workflows anyway.

## Materialization

What a job did must outlive the try that did it: a retry, a runner restart
or a judgement after the fact all need the events of every try. They live in
Postgres, through `common/factory_store` (package `factory_store`): the
schema (SQLAlchemy Core), the migrations (alembic) and one small async
`Store` API. The app and the runner both write through it; it imports
neither.

Tables, one job = one session:

- `session` — the coder's session id (the job's key), provider, model,
  workdir, prompt, created_at. Written by the `create_session` activity.
- `attempt` — one row per try: attempt number, started_at, ended_at,
  outcome `running | done | failed`, failure text, the try's totals
  (input, output, cache read and cache write tokens, cost, duration,
  turns, tool calls, tool failures; flat columns so sql can sum them) and
  the `JobResult` as json (`{}` on failure). Opened by the journal
  callback's `on_start`, closed by its `on_end`, on success, on a
  `JobFailed` and on cancellation, with what the engine's ledger counted
  so far. A try still marked running when a later try of the session
  starts died with its runner; the store closes it as abandoned then.
- `event` — one row per event, the whole `Event` as json (`raw` line
  included), with the try it belongs to and the coder's timestamp. Written
  by `JournalCallback` (`callbacks/journal.py`), one of the job activity's
  callbacks next to heartbeat and log. The row id is the order of the
  session across tries and runner restarts; a sequence number kept in
  memory would restart with the process, and timestamps from two tries
  can overlap when an orphaned coder is still writing.
- `conversation` — the session rendered as one transcript, built once at
  the end by `job/report/conversation.py`: the user's request from the
  `session` row (the coder never echoes it, so it is not an event), then
  a header per try, the model's text,
  its tool calls with clipped arguments, tool outputs clipped in the middle,
  rate limits, compactions, the finish line. Clip sizes are settings.
- `report` — the `JobResult` as json (empty when every try failed), the
  `JobReport` the model wrote, and its verdict as a column.
- `structured_output` — for a job a workflow asked for one: the JSON
  schema it asked for, the output the extraction step found, and where
  (`last_message | conversation`). Written by the
  `extract_structured_output` activity once the step found it; a job whose
  output was not stated has no row.
- `job` — one row per workflow run, written last: first try's start, end
  time, number of tries, outcome `done | failed`, failure text, the
  totals summed over every try (same columns as `attempt`), the result as
  json and the report's verdict. The one row to query when the question
  is what a job cost or how it ended; the tries are the detail.

The flow in the runner: `create_session` → `start_session`; each
`execute_job` try → `start_try`, events, `finish_try` (all three from the
journal callback); then the `build_report` activity loads every event,
renders and saves the conversation, runs the report step and saves the
report; then `record_job` sums the tries into the `job` row. The workflow
runs the report after the job activity whatever happened to the job: a
permanently failed job gets a report on its failure. A failed report step
is not fatal, the outcome just has no report; a failed record is not
fatal either. `JobWorkflow` returns a `JobOutcome`: session id, result or
failure text, report.

Postgres runs from `docker-compose.yml` (`just db` starts it and applies the
migrations, `just db-stop` stops it, the data stays in a volume). Tests use an
in-memory SQLite through the same schema, so no test needs the database.
The url is the shared setting `store.url` in `common/factory_settings`
(override with `AF_STORE__URL`); the runner and the migrations read the same value.

## Settings

Every default lives in `agentic_factory/settings/settings.toml`: job limits, the
default provider of jobs and steps, each harness's and client's default model,
the Go base url and user agent, reasoning and token limits of steps.
`settings/load.py` loads it with dynaconf and validates it into the pydantic
models of `settings/model.py`, so code reads `settings.step.max_tokens`, never a bare key.
The runner package repeats the pattern for its own `[temporal]`, `[runner]`,
`[cli]` and activity tables. The loader itself lives once, in
`common/factory_settings` (`load(model, folder)`), which also holds the
values more than one package needs: the store's url in `[store]`. Every
settings model is a `Table` with `extra="forbid"`, so a misspelled key in a
toml file or an `AF_` variable is refused on load instead of ignored.
The conversation's clip sizes are `[conversation]`, the report's transcript
limit `[report]`, the structured output extraction's text limit
`[structured_output]`.
Overrides, in order: `settings.local.toml` next to it (git-ignored), a
`.env` found walking up from the package (repo root or `~/.env`), and
environment variables `AF_<TABLE>__<KEY>`. `Job` and `Step` take their
field defaults from there, and the CLIs pass on only the flags given, so no
default is repeated in Python.

## step contract

Lives in `agentic_factory/step/`, shaped like `job/`: `contract.py` is the
contract, `providers/client.py` the client base (as `job/coders/harness.py` is the coder
base), `providers/catalog.py` picks a client by provider name, `engine.py` runs one
step, and one folder per provider holds the wire code. One request, one JSON
answer, no tools. Used inside workflows to turn events or artifacts into
typed data (a report from a job's stream, a status from a helper's notes).
Renamed from "llm call" Sep 2026.

- `Step` — provider (default opencode), prompt, `output_schema` (a JSON
  schema dict, usually `SomeModel.model_json_schema()`, so the shape is
  decided by the caller), system_prompt (standing instructions), model (empty
  = client default), reasoning (minimal … high, default high), max_tokens,
  timeout_sec. Serializable, so it can be an activity argument.
- `StepResult` — `output` (the answer as a dict), model, tokens,
  duration_sec. `result.parse(SomeModel)` gives the typed object and raises
  `BadOutput` if the answer misses the schema.
- `Client` — abstract base, one subclass per provider: `from_env()` builds
  it from keys in the environment, `complete(step)` sends the step and
  returns an `Answer` (text, tokens), raising `RateLimited`, `TimedOut`,
  `NetworkError`, `ProviderError` or `BadOutput` (cut off) when there is
  none. Each client names its `default_model`.
- `run(step, callback, client) -> StepResult` in `step/engine.py` —
  the single entry point, the twin of the job engine. Takes the client
  the caller picked, fills the default model, enforces `timeout_sec`, emits one
  `ai` event with the answer text and one `finished` event to the callback
  (a step has no start and end of its own),
  reads the text as a JSON object (`BadOutput` otherwise), and returns the
  result.
- `OpencodeGo` in `providers/opencode/client.py` — the OpenCode Go API through the
  `openai` SDK. Picks the wire protocol from the model name (chat
  completions by default, Responses for muse-spark, grok and gpt) and sends
  the schema as a strict `json_schema` format. Default model
  `muse-spark-1.3-contributor` (about 5 s at low reasoning). No retries in
  the client; Temporal retries.
- `scripts/run_step.py` behind `just step` runs one from the CLI, as
  `scripts/run_job.py` behind `just run` runs a job. The scripts are dev
  entry points outside the package; the just recipe carries the demo input.
  Both take `--json`, which swaps the human log on stderr for
  `JsonLinesCallback`: one JSON object per event on stdout, no prefix, for
  a log shipper or `jq`.

Learned from probes (Go API, Sep 2026): the `openai` SDK works once the
user agent is overridden; each request needs a fresh `x-opencode-session`;
reasoning models spend most output tokens thinking, so `max_tokens` must
leave room; glm-5.3-flash without a reasoning effort took 30 s, with `low`
6 s.

Small results live in Temporal history. Large deliverables live in an
artifact store keyed by run / job / try, referenced by path. The
store exists so a run can be re-executed from step N reusing earlier
results, and for human review. It is a store of outputs, not of
process state. No task.json, no attempts log, no signal files.

## Judge step

Lives in `agentic_factory/step/judge/`: the second kind of step. The llm
step takes a prompt and a schema and gets text shaped to the schema; the
judge step takes a **state** (text or JSON) and named **questions** and
gets **answers with probabilities** back. No prompt, no schema, no tools.
Used where a workflow branches on a judgment: rank papers by relevance,
accept or reject a draft, route a ticket. The TypeSafe jev model answers
in well under a second and bills input tokens only; the client's price
per million lives in settings so the result carries `cost_usd`.

- Questions: `Choice(question, options: name -> meaning, focus)`,
  `Score(question, levels lowest first, focus)`, `Check(question, yes, no,
  focus)`. `focus` is what the judge should attend to in the state.
- `Judgment` — provider (default typesafe), state, questions (at least
  one), model (empty = client default), timeout_sec (settings).
- `JudgmentResult` — answers by name, model, tokens, cost_usd,
  duration_sec. `.choice(name)`, `.score(name)`, `.check(name)` return the
  typed answer or raise `BadOutput` when the name or kind does not match.
- Answers: `ChoiceAnswer(choice, confidence, probabilities)`,
  `ScoreAnswer(score, confidence, probabilities, legend)` keyed by level
  index, `CheckAnswer(yes)` the probability of yes.
- `JudgeClient` is the client base (`client.py`), `catalog.py` picks one
  by provider name, `typesafe.py` is the only client so far; failures map
  to the same `JobFailed` family as the llm step (`RateLimited` carries the
  retry-after, `TimedOut`, `NetworkError`, `ProviderError`).
- `engine.run(judgment, callback, client)` emits one AI event (the answers
  as JSON, usage, cost) and a FINISHED event, then returns the result.
- Runner: `activities/judge.py` is the activity, `workflows/judge.py::run_judgment`
  calls it with the judgment's timeout plus `[judge_activity]` margin and
  the table's retry policy. `just judge` in the app runs one from the CLI.

## Decisions so far

- Runs on the user's laptop / server. Temporal is the `temporal` CLI dev
  server, not docker: one binary, history in a SQLite file under
  `~/.local/share/agentic_factory/`, web UI on :8233. `just temporal-install`,
  `just temporal`, `just temporal-health`; `just temporal-tailscale` also opens the UI
  to other tailnet devices at the machine's Tailscale IP. Clients use `127.0.0.1:7233`, never
  `localhost`: on macOS that resolves to IPv6 first and the server is IPv4
  only, so gRPC hangs. Postgres, for the store, runs from the repo's
  docker compose (`just db`); the runner keeps running on the host either
  way, since it needs the coder CLIs, their auth stores and the worktrees.
- The UI knows the job. `search_attributes.py` names six Keyword search
  attributes the server indexes: `Provider`, `Model`, `Workdir` set by the
  cli when it starts the workflow, `Runner` upserted by the workflow after
  the job activity (the identity of the runner that ran its last try, from
  the activity's `TryResult` or the `ActivityError`), `Outcome` (`done` |
  `failed`) and `Verdict` upserted at the end. The UI lists them as
  columns and takes them in filters (`Provider="claude" AND Outcome="failed"`).
  They must exist on the server first: `just temporal-attributes` (the cli's
  `attributes` command) adds the missing ones once; a start with an unknown
  attribute is refused, an upsert of one blocks the workflow task. The
  runner polls as `host:pid:sha` (`identity.py`), which the task queue's
  workers page and every `ActivityTaskStarted` event show.
- Harness calls preferred over API calls for cost; both are activities.
- Steps go to the OpenCode Go API (`https://opencode.ai/zen/go/v1`),
  covered by the same subscription as the opencode CLI. Key in
  `OPENCODE_API_KEY`; see `.env.example`. The endpoint needs a stable
  `x-opencode-session` header and a client-specific user agent. Each
  model speaks one protocol: chat completions (glm, kimi, deepseek,
  longcat) or Responses (muse-spark, grok, gpt luna).
- Beads is an input source (watcher) and an output target (a workflow
  updates status), not the internal state store.
- One watcher at most (beads). X monitoring is a schedule whose first
  activity runs `x watch check`.
- No YAML workflow language. Graphs are Python; a data-driven DAG
  interpreter can be added later if needed.
- Langfuse from milestone one, since the stream parser is needed anyway.

## First milestone

One job, started manually from the CLI on Temporal, returning
a `JobResult` with a report, with retries classified by cause. Everything
else layers on top.
