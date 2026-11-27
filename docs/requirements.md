# Requirements and planned work

[Magyar](requirements.hu.md)

What the planned parts have to do. Task numbers refer to the [roadmap](roadmap.md), which also holds the statuses.

## How requirements are written

Adopted on 2026-11-27 for new requirements; the existing ones are reviewed against it in task 26. Based on the quality
criteria of the IREB CPRE Foundation Level, ISO/IEC/IEEE 29148 and ISO 26262-8, clause 6.

**Each requirement is**

| Criterion | Meaning | Check |
|---|---|---|
| Necessary | Removing it would leave a need or a known failure uncovered | The reason column names the need, decision or observation |
| Unambiguous | One reading only; no "fast", "robust", "user-friendly", "etc.", "if possible" | Numbers with units, named fields, enumerations |
| Singular (atomic) | One statement; no "and" joining two obligations | Split into two IDs if two tests would be needed |
| Verifiable | A test, a review step or a measurement can show it is met | The verification column is filled (see below) |
| Feasible | Achievable with the known environment and dependencies | Unknowns are listed as open items, not as requirements |
| Consistent | Contradicts no other requirement or decision | A conflict is resolved before both are kept |
| Complete | States the condition, the actor or component and the expected result | Form: "When <condition>, <component> <does> <result>" where a condition applies |
| Free of solution detail | States what and why; how only where the "how" is the decision itself | Implementation notes go to the architecture document |

**The set of requirements is** organized by component, without duplicates, with stable IDs (an ID is never reused;
a dropped requirement keeps its ID with the note "withdrawn"), bilingual with the same IDs in both languages, and
traceable to tests (task 25).

**Form.** A table per area with the columns ID, requirement, reason and, from task 26 on, verification (`test`,
`live`, `review` or `measurement`). "Must" marks an obligation; "should" is not used. Statuses stay in the roadmap.

## 1. Interface

- Start, pause, resume, stop; live status.
- Views: Pareto scatter plot (VRAM vs speed, point size = context length), model × test suite heatmap, radar chart for
  2–4 models, filterable table with Excel export.
- Agent views (data from the core, see FA-43 and FA-47): failure category heatmap (model × category), composition
  of failures (stacked bars, treemap or sunburst over level, category and subcode), share of silent failures per
  model, primary to secondary categories (Sankey); per attempt a timeline of rounds and tool calls and a step view
  with the evidence event highlighted.
- Warning at measurement time: the browser uses VRAM and GPU.
- Measure the browser overhead on a fixed configuration: dashboard closed / open with hardware acceleration / open
  without it. Include an offloaded configuration (without acceleration the CPU load rises). How to read per-process VRAM
  still has to be checked (`nvidia-smi` returns `N/A` on the development machine).
- Each result row records whether the dashboard was open during the measurement.
- The built frontend can be shipped, so that using it does not require Node.js.
- Switching between English and Hungarian; texts in language files, English is the default.

## 2. Testing (planned)

- Python logic and FastAPI: `pytest` (it can run the existing `unittest` tests).
- React components: Vitest + React Testing Library.
- End to end: Playwright, with a fake runner and recorded sample results, without a GPU. Not run during measurements.
- Live GPU tests are separate and started manually (`tests\live_control_test.py`).

## 3. Agent harness and failure analysis: initial requirements

Draft, to be detailed before step G.

### Harness

- Written in TypeScript, talking to LM Studio through the official SDK if the trial (task 18) succeeds.
- Runs a model in a tool loop. The first version has file reading and mock tools only (mock tools give deterministic
  tests); search, git and shell follow after the sandbox decision.
- Everything runs in a throwaway sandbox folder; no network by default.
- Limits: timeout per tool call, maximum number of steps per task, no endless retries; the user is told when a limit is hit.
- Interruption and resume; clean recovery from tool errors and invalid model output.
- Context handling: conversation history, tool results, what happens when the context fills up.
- Usable from the CLI first, like every other feature.

### Failure analysis

- Every step is logged: prompt, model output, tool call, tool result, timing, tokens.
- Failure categories (first set): invalid tool-call format, wrong tool, wrong arguments, ignored tool error, endless
  retrying or looping, limit hit without telling the user, context overflow, task result wrong despite correct steps.
- Each category is described FMEA-style: failure mode, effect, how it is detected, mitigation. The report suggests
  mitigations, it does not only count.
- Report per model and per task: success rate, categories, longest reliable chain length.
- Tasks are fixed and reproducible, with pass/fail checks; each runs several times to show the spread.
- Compare model-specific tool-call formats, where the JSON breaks, and which repair helps (retry, schema constraint,
  grammar).
- Interrupt and recovery cases: stop during a tool call, truncated output, resume.
- Second round (after M1): context truncation and summarization, tool result size limits, behaviour as context grows.

### Interface to the core (decided and implemented 2026-11-26)

| ID | Decision | Reason |
|---|---|---|
| H1 | The core starts one `node harness/run-tasks.ts` process per model and task set. The spec is the first stdin line (JSON); the last stdout line is `RESULT:` followed by a JSON summary | Same pattern as the loader; a crash stays in one process; simple on Windows. Rejected: a long-lived JSON-RPC process, HTTP |
| H2 | The harness does not load models; it receives the `identifier` of a model the existing loader loaded | One load path with the existing checks |
| H3 | Stop arrives as a further stdin line (`{"cmd":"stop"}`) and triggers an `AbortSignal`; the trace records `aborted`. After a grace period the core kills the process | Windows has no reliable signal for a child process |
| H4 | Trace: JSONL per task run with `schema_version`; events `task_start`, `prediction` (raw text, tokens, timing), `tool_call` (raw and parsed arguments, validation error), `tool_result` (size, error, duration), `limit_hit`, `error`, `task_end` | Appendable, readable even with a broken last line |
| H5 | Pass/fail checks and failure categorization run in the Python core, from the trace and the kept final state of the sandbox; the harness only executes and logs | Logic lives in the core and is reachable from the CLI |
| H6 | Own tool loop behind a `ModelBackend` interface: `LmsSdkBackend` (one prediction round with `respond()` and `rawTools`) and `ScriptedBackend` (deterministic offline tests without a GPU) | Invalid tool calls must be logged raw; `.act()` throws on an unparseable call. Single-round tool calls exist in the SDK 2.1.0 types; a short live check is still needed |
| H7 | M1 scope: tools `read_file` (path resolved inside the sandbox, size limit) and `mock_lookup` (deterministic, configurable delay and error for timeout cases); limits per tool call, rounds and total time; a throwaway sandbox folder per task with a copy of the fixtures; no shell; CLI command `bench agent run` | Thin M1 slice; the sandbox decision for shell commands can wait |

**Live check of H6 (2026-11-26, `harness/tools-probe.ts`, three models at 4k context, temperature 0):**

- `respond()` with `rawTools` works for one round: with a model that uses the expected tool-call format the callbacks
  arrive in order (start, name, argument fragments, end with the parsed request and the raw arguments), and the stop
  reason is `toolCalls`. Sending the tool result back as a `tool` message gives a correct final answer.
- A 7B coder model wrote the tool call as JSON inside a fenced text block. The SDK did not recognize it: no tool-call
  callback, stop reason `eosFound`. Only the raw text shows the attempt, which confirms that the harness must log raw
  output and that repairs (task 19) are needed. A 1B model did not call a tool and answered without the data.
- No model needed a tool for a simple sum, and none called one.
- An abort through the `AbortSignal` ends the prediction with stop reason `userStopped` and the partial text, without
  an exception.
- `content` contains the reasoning text of thinking models; the harness has to use `nonReasoningContent`. After an
  abort during reasoning, an internal LM Studio separator string appeared in `content`.
- No `onToolCallRequestFailure` callback was seen.

**M1 implementation (2026-11-26):** `bench agent run` (`runner/agent.py`, `harness/run-tasks.ts`, `harness/agent/`)
implements H1–H7. Further details fixed by the implementation:

- Task files (`tasks/*.json`, `schema_version` 1) hold per task: prompt, optional system prompt, fixture folder, tools,
  mock table (result, error, delay per id), limit overrides and declarative checks: `answer_contains`,
  `answer_contains_any`, `tool_called`, `tool_not_called` (`*` for any tool), `mentions_failure`. Checks compare the
  final answer case-insensitively; only tool calls the SDK parsed count as called.
- Default limits: 6 tool rounds, 10 s per tool call, 180 s per attempt, 8000 characters per tool result, 2048 tokens
  per round. When the round limit is hit, the model gets one more round without tools and a note to answer the user;
  the attempt ends with status `limit`.
- An unknown tool or invalid arguments go back to the model as an error result; a tool call the SDK could not parse is
  logged raw and ends the attempt (no repair in M1).
- An attempt is passed when it ended `done` or `limit` and all its checks hold.
- The scripted backend runs the whole path offline (`bench agent run --scripted <file>`), which the Python tests use.

First live run with the four example tasks (file read, order lookup, tool error, tool timeout), temperature 0: an 8B
reasoning model passed 4 of 4; a 7B coder model passed 0 of 4 because it wrote every tool call as text.

The headless assistant beta API of the LM Studio Bionic application (listed in the 1.2.1 release notes) is not used in
M1; the installed version is 1.2.0.

### Failure analysis plan for M1 step 5 (agreed 2026-11-26)

M1 step 5 turns the harness into a measurement: a fixed task set, repeated attempts and a report that explains why a
model fails. The plan was reviewed independently before it was accepted; the review's findings are folded in below,
with the reason for each requirement, so that the decisions can be re-examined later.

The step is split in two. **5a, foundations:** a live pre-check of sampling, additional trace fields, the task format v2
with declarative mock tools, the categorizer and the taxonomy document. **5b, measurement:** the 20-task set with
reference solutions, the report and the live runs. The split lets the categorizer be checked on synthetic and existing
live traces before effort goes into the tasks.

**Task format (v2, own schema version)**

| ID | Requirement | Reason |
|---|---|---|
| FA-01 | Mock tools are declared in the task file (`toolsets`: name, description, parameter schema, response rules); tasks refer to them by name. `read_file` stays a built-in tool | New tools and tasks without code changes |
| FA-02 | Response rules: the first matching rule wins (argument condition: `equals`, `one_of`, `any`); a rule can answer by call count (`sequence`, for "pending" and transient-error tasks); a default answer is required. No template language | Deterministic, reviewable tool behaviour |
| FA-03 | Tool arguments are validated against a schema subset (`type`, `enum`, `required`) without a new dependency; a number sent as a string is `wrong_type`, not silently converted | Small models often get types wrong; that is data, not noise |
| FA-04 | `expected_calls` is an ordered subsequence with argument matchers: the minimal call sequence must appear, extra calls are allowed and only flagged. `forbidden_tools` lists calls that fail the attempt | Exact matching would punish recovery from errors and harmless extra calls (the reason BFCL v3 moved to subsequence matching) |
| FA-05 | Values a correct answer needs are unique, unguessable tokens; in chains the next argument comes from the previous result | A correct answer cannot appear without the tool calls; the order is forced by the data, not by the check |
| FA-06 | `answer_not_contains` (deny list) next to the keyword checks | A keyword such as "error" can sit next to an invented result; a value the model cannot know is a sure sign of fabrication |
| FA-07 | An attempt that ends with status `limit` fails unless the task accepts it | Otherwise a model that repeats until the round limit and answers after the harness note looks successful |
| FA-08 | Every task has a scripted reference solution that passes and at least one scripted reply that fails with the expected category | Tests the task and the categorizer together |

**Trace and run metadata**

| ID | Requirement | Reason |
|---|---|---|
| FA-10 | `task_start` records run and attempt ids, model key, context length, the sampling settings actually sent, the system prompt, a hash of the offered tool schemas, a hash of the task file and the harness version | A trace must be re-evaluable on its own |
| FA-11 | `prediction` records its start time and duration; `tool_call` and `tool_result` carry an own call sequence number next to the model's call id (which may be missing); `tool_result` carries an `errorKind` (`not_found`, `outside_sandbox`, `invalid_arguments`, `unknown_tool`, `timeout`, `mock_error`, `cancelled`) | The categorizer must not match error texts; round duration is not readable today |
| FA-12 | Separate schema versions for the task file and the trace | They change at different times |
| FA-13 | The harness asks LM Studio to stop at the context limit (`contextOverflowPolicy: stopAtLimit`) | The other policies truncate silently, which would hide context overflow |
| FA-14 | A flat event trace stays; no span tree yet. The fields above keep a later export to OpenTelemetry GenAI spans lossless (attempt → `invoke_agent`, prediction → `chat`, tool call and result → `execute_tool`, `errorKind` → `error.type`) | One agent and three levels gain nothing from a span tree; a span is written when it closes, so an interrupted run would lose it; the convention is still in development |

**Sampling**

| ID | Requirement | Reason |
|---|---|---|
| FA-20 | A sampling profile per model family (temperature, top_p, top_k, min_p, repeat penalty, source URL) in a config file, with 0.7 as the fallback temperature; `--temperature` overrides; the harness sends every value explicitly | Today only the temperature is sent; the rest comes from LM Studio defaults, so results are not reproducible. Model cards differ (Qwen3 discourages greedy decoding) |
| FA-21 | Before the task set is written, a live check: one task, five attempts at a temperature above 0; do the outputs differ? | The seed is a load parameter; if repeats were identical, repeating would measure nothing |

**Categories and priority**

| ID | Requirement | Reason |
|---|---|---|
| FA-30 | Few top-level categories, details as subcodes (list in the [failure taxonomy](failure_taxonomy.md)); every failed attempt gets exactly one primary category, further findings are secondary | 100–200 attempts per model would be spread too thin over many categories |
| FA-31 | Three levels: structural (fixed order), behavioural (the detector whose first evidence comes earliest in the trace wins), outcome (fixed order, only if no behavioural finding) | A fixed global order misjudges chains of consequences (wrong argument → tool error → repetition → round limit); the cause shows in the time order |
| FA-32 | Every finding carries evidence: trace file, event sequence number, rule name | Turns the report into diagnosis |
| FA-33 | A text tool call (a call written as text in the answer, naming an offered tool in call form) is `format_invalid/text_tool_call`, not "no tool called" | Observed live: such a reply has no tool-call event at all |
| FA-34 | `unclassified` for failures no rule explains; its share measures the taxonomy's coverage | Without it the last category becomes a catch-all |
| FA-35 | Failures are also classed as silent (the user cannot notice: wrong result, invented value, hidden limit) or loud | The headline number of the report; it corresponds to an undetected fault in functional safety |
| FA-36 | Secondary flags also on successful attempts: `recovered_error`, `redundant_calls`, `parallel_calls`, `reasoning_leak`, `sandbox_escape_attempt` | Recovery is the baseline for task 19; a reasoning leak can make a check pass falsely |
| FA-37 | Heuristic rules are marked as such; their agreement with a manual review of about 50 failed attempts is published | Keyword rules have false positives and negatives |
| FA-38 | One machine-readable source of the categories (id, level, silent or loud, reliability); a test checks that each id appears in the English and Hungarian taxonomy document | Keeps code and documents in step |
| FA-39 | If almost all failures of a model are `format_invalid`, the report says that its other abilities could not be measured | Zeros would be misleading |

**Runs and report (5b)**

| ID | Requirement | Reason |
|---|---|---|
| FA-40 | `bench agent run --models a,b,c` runs the models one after another; an error of one model is recorded and the next one runs | One comparison table |
| FA-41 | If the harness ends without a result line, the core rebuilds the attempts from the traces | Today a killed harness loses every result |
| FA-42 | The run's time limit is computed from tasks, repeats and the attempt limit; the task file is copied into the run folder; result rows carry the taxonomy version | Slow models; later re-evaluation |
| FA-43 | `bench agent report` recomputes categories from the traces and writes Markdown and JSON: per model and task the success rate with a Wilson interval, categories, median rounds and time, pass^k, the share of silent failures; also a model × category matrix and the counts of primary → secondary category pairs, as text | Small samples need intervals; pass^k shows reliability in one number |
| FA-44 | Longest reliable chain: two tasks per chain length, ten attempts each; a length counts when at least 16 of 20 attempts pass and every shorter length counts too | One task × 5 is noisy and not monotonic (≥4/5 lets a 60 % model through in about one case in three) |
| FA-45 | Five repeats by default, ten for published tables | 5/5 has a Wilson interval of 0.57–1.00 |
| FA-46 | Mitigations are shown as "possible mitigation (not measured)" until task 19 measures them | No claim without measurement |
| FA-47 | `bench agent show <run> <task-attempt>` prints an attempt's steps with their sequence numbers (predictions, tool calls with arguments, results with error kind, limits) and marks the evidence event of its category | The manual review of FA-37 needs a readable view of a trace; the same data feeds the graphical step view later |

**Status of 5a (2026-11-26).** Implemented and covered by offline tests: FA-01 to FA-07, FA-10 to FA-14, FA-20,
FA-30 to FA-36, FA-38, FA-41 (rebuild from traces) and the run folder copy of the task file from FA-42; default
repeats raised to 5 (FA-45). FA-21, live: five attempts of one task on an 8B reasoning model at temperature 0.7 gave
five different reasoning texts and the same final answer, so repeats do measure variation. Live check on 2026-11-27: the prediction config LM Studio reports back shows every
sampling value of the profile and `stopAtLimit` applied, and the trace now records it (`applied` in `prediction`);
the four example tasks passed 4 of 4 on the 8B reasoning model, and all four failures of the 7B coder model were
categorized `format_invalid/text_tool_call`. Open for 5b: FA-08 (with
the task set), FA-37, FA-39, FA-40, the computed time limit of FA-42, FA-43, FA-44, FA-46, FA-47.

**Task set (5b), 20 tasks:** direct single tool (2), tool choice among close decoys including a destructive one (2),
exact arguments: types, a hard identifier, a missing required parameter where asking back is correct (3), chains of 2,
3 and 4 steps (1 + 2 + 2), tool error, missing file and a transient error that justifies one retry (3), timeout with a
deny list (1), no tool needed: knowledge, answer already in the prompt, needed tool not offered (3), a "pending, check
again" tool where success means stopping on its own within a call budget (1).

**Out of M1:** language switch as a category, mandatory parallel calls, prompt injection in tool results, truncated
large tool results (task 22), FMEA risk priority numbers (measured frequency and the silent / loud class instead),
automatic choice of mitigations, the 14B model as a required row.

### Open

- How the sandbox restricts model-generated shell commands. This must be decided before any such command is executed.
- Finding LM Studio's API port for the SDK without an internal file.

## 4. Investigation: is a model biased?

Task 23. Status: not examined; nothing below has been reproduced in this project.

**Question.** Does a model behave differently when only a detail that should not matter changes? Which factors trigger
this, and how does it differ between models, model families and original and modified ("uncensored") variants?

### Stages

1. Research: on which factors models can be biased (for example requester, purpose, nationality, political topic), in
   which outputs it shows (refusal, content and tone, quality, security of generated code), and which measurement
   methods are published.
2. Test prompts for each factor: sets that differ only in that factor, with neutral controls and a metric per output
   type; reviewed before the first run.
3. Measurement per model.
4. Report per model.

### General requirements

- Factors, prompts and metrics fixed before the first run; at least two neutral wordings to estimate the noise of the
  wording itself.
- Objective metrics where possible. Where outputs are graded, a written rubric and a check of the grader's own bias (a
  grading model can be biased too).
- Statistics with confidence intervals and correction for multiple comparisons.

Text-only tests depend on the fixed task set (task 20); tests that run generated code also need the harness and failure
analysis (tasks 16 and 17). Scheduled after M1.

### First known case: requester-dependent code security

With the same coding task, does the share of exploitable code change when only the stated requester or purpose differs?
It fits the cybersecurity quality suite (task 6).

**Published claims**

- [Hirundo, 2026-10-21](https://www.hirundo.io/blog/qwen3-coder-vulnerabilities), Qwen3-Coder-30B-A3B-Instruct, one
  phrase changed in the system prompt, one task (BaxBench SecretStorage), temperature 0.6, mostly 190 generated apps per
  persona, detection by running exploits. Apps for a US defense contractor were exploitable in 70% of cases, for a
  Chinese one in 59% (p = 0.03). With a Hong Kong democracy group, apps leaking other users' secrets were 28% more
  frequent (relative) than with neutral prompts (p = 0.024).
- [CrowdStrike, 2025-11-20](https://www.crowdstrike.com/en-us/blog/crowdstrike-researchers-identify-hidden-vulnerabilities-ai-coded-software/),
  DeepSeek-R1: more severe vulnerabilities with politically sensitive terms in the prompt (known here only from a
  search summary).

**Limits of the Hirundo study.** Vendor study (the company sells the remedy), not peer reviewed. The task shown stood
out among eleven screened ones. With about ten comparisons, p values near 0.03 would not survive a correction for
multiple testing. The blog post links no study prompts, code or raw data. The authors do not claim to know whether the
effect is intentional.

**Additional requirements for an own measurement**

- Several coding tasks, chosen before the first run.
- Detection by running exploit tests; static analysis alone is not enough (the study reports 2 apps flagged by static
  analysis against 1144 broken by attacks, out of 1840).
- Sample size: detecting a 59% / 70% difference with 80% power needs about 300 samples per condition (own estimate,
  one comparison, 5% significance).
- Generated code runs only in an isolated sandbox; this depends on the sandbox decision of section 3.
- The Hirundo results concern a 30B model; they say nothing about the smaller models that fit the 8 GB development GPU.

## 5. Speculative decoding

Task 24. Status: not tried; no measurement has been made.

**Goal.** Treat speculative decoding as its own optimization dimension: per model and task type, measure the speed gain
and the resource cost against the same configuration with speculation off, then recommend a setting, which may be "off".

### Known about the installed version

Read from the type definitions of `@lmstudio/sdk` 2.1.0 and from earlier observations; nothing was verified by running a
speculative load.

- Load config (marked experimental): `speculativeDraftMtp` (bundled multi-token prediction heads),
  `speculativeDraftSimple` with `speculativeDraftModel` (separate draft model), `speculativeDraftMaxTokens`,
  `speculativeDraftMinTokens`, `speculativeDraftMinContinueProbability`. The sweep runner sends the first two as `false`,
  and they appear in the applied configuration read back after the load.
- Predictions through the SDK accept `draftModel` and report `usedDraftModelKey`, `totalDraftTokensCount`,
  `acceptedDraftTokensCount`, `rejectedDraftTokensCount` and `ignoredDraftTokensCount`.
- `lms load` lists `--speculative-draft-*` options and the REST load call accepts speculative fields
  ([load parameters](lmstudio_load_parameters.md)).
- Whether the REST chat endpoint used for measurement returns draft counters is unknown.
- Documentation: [LM Studio](https://lmstudio.ai/docs/app/advanced/speculative-decoding),
  [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md). The upstream llama.cpp offers more
  methods than are known to be reachable through LM Studio.

### Phases

| Phase | Content | Exit criterion |
|---|---|---|
| 0, trial | Load with a draft model and with MTP through the SDK; read back the configuration; draft statistics through the SDK and the REST chat call; extra VRAM; whether a setting persists into later loads | Written capability table and a decision on how to switch MTP |
| 1 | LM Studio: off, draft model, MTP | A reproducible comparison on at least one model |
| 2, optional | Direct `llama-server` backend for further methods (n-gram, EAGLE-3, DFlash and similar) | Measured into the same result format; only after a separate decision |

Training draft models is out of scope. Downloading draft models or running third-party builds needs approval each time.

### Phase 0 trial plan (agreed and run 2026-11-26)

Boundaries: a standalone probe script (`harness/spec-probe.ts`), no grid integration, no application, runtime or SDK
update, LM Studio settings files untouched. Models: a 7B coder model with a small draft model of the same family at 4k
context (headroom on the 8 GB GPU), and the locally available MTP models; their model cards are read first for usage
notes.

| Step | Content | GPU |
|---|---|---|
| P0 | Probe script, type check, hash of the LM Studio config folder. Done: `harness/spec-probe.ts` with offline tests and `--dry-run`; a real type check needs a TypeScript compiler, not installed | no |
| P1 | Baseline with speculation off: VRAM, decode speed (warm-up and 3 runs), with a code-generation and the synthetic prompt | yes |
| P2 | Draft model set at load: applied configuration read back, extra VRAM, whether the draft shows as a separately loaded model, draft counters, speed | yes |
| P3 | Draft model set per prediction (`draftModel`) on a baseline load: statistics and speed | yes |
| P4 | The same through the REST chat endpoint: raw response fields stored, are draft counters present | yes |
| P5 | MTP on and off; a load failure is a reasoned "skipped" result | yes |
| P6 | Persistence: reload with the speculative fields omitted and read back; switch from draft to MTP; config folder hash compared; an incompatible pair to see the error (SD-01) | yes |
| P7 | Capability table into this section; findings and load parameter notes updated | no |

Acceptance: every question of P1–P6 has a status (verified, does not work, blocked); every result records the
application and runtime versions and the background VRAM use; the config folder is unchanged; no model is left loaded;
about one hour of GPU time at most. Each GPU run is started only after approval.

### Phase 0 results (2026-11-26, run on the GPU)

Bionic 1.2.0, RTX 2070 8 GB, 4k context, full offload, f16 KV, temperature 0, warm-up and 3 runs of 200 output tokens
per prompt. The probe's raw results stay local.

| Question | Result | Status |
|---|---|---|
| Draft model at load (`speculativeDraftSimple` + `speculativeDraftModel`) | Applied and read back as requested. LM Studio defaults: 3 max draft tokens, minimum 0, continue probability 0 | verified |
| Draft model per prediction (`draftModel`) | Refused by the engine: speculative decoding must be configured at load time | does not work in this version |
| MTP at load (`speculativeDraftMtp`) | Applied and read back; draft counters present | verified |
| Draft counters in the SDK | `usedDraftModelKey`, total, accepted, rejected; `ignoredDraftTokensCount` is not returned | verified |
| Draft counters in the REST chat endpoint | A `stats` object (`draft_model`, `total_draft_tokens_count`, `accepted_draft_tokens_count`, `rejected_draft_tokens_count`) in the non-streamed response and in the last streamed chunk with `stream_options.include_usage` | verified |
| Draft model in `lms ps` | Not listed; only the main model shows, the cost appears only as VRAM | verified |
| Extra VRAM | Draft model (1.5B, Q8_0): about +1.2 GiB. MTP on and off: no difference (the heads seem to be loaded either way; inference) | verified, one measurement each |
| Persistence | A later load that omits the speculative fields gets them off; a draft load followed by an MTP load leaves no draft model; the per-model config folder stays unchanged | verified |
| Incompatible pair | A 1B Llama target with a 1.5B Qwen draft loads and answers, `usedDraftModelKey` is set, no counters. LM Studio does not reject it | verified; SD-01 needs its own compatibility check |
| Greedy output against the baseline | With speculation on, most runs differ after 20 to 800 characters; the cause was not examined | observed |

Decode speed, median of 3 (code prompt / synthetic prompt), all with the default of 3 max draft tokens:

| Setup | Off, t/s | On, t/s | Change | Acceptance rate |
|---|---|---|---|---|
| 7B coder model + 1.5B Q8_0 draft of the same family | 63.4 / 60.6 | 55.8 / 34.2 | −12% / −44% | 0.76 / 0.36 |
| 4B model, built-in MTP head | 78.5 / 77.1 | 96.4 / 96.5 | +23% / +25% | 0.70 / 0.72 |
| 9B finetune, MTP head grafted from its base | 50.3 / 49.0 | 54.8 / 65.3 | +9% / +33% | 0.54 / 0.72 |
| 0.8B model, built-in MTP head | 156.9 / 152.1 | 163.5 / 179.0 | +4% / +18% | 0.51 / 0.66 |

These are single trial runs, not a comparison by SD-02 to SD-07.

**Decision (phase 0 exit criterion):** speculation is switched only at load, through the SDK load fields: MTP with
`speculativeDraftMtp`, a draft model with `speculativeDraftSimple` and `speculativeDraftModel`. Phase 1 can keep the
current loader and measure over the REST endpoint, which returns the counters. Phase 1 adds: a sweep of the maximum
draft tokens (model cards suggest 2 to 6), a compatibility check for draft pairs (tokenizer), and smaller draft models.

### Requirements

"Today" describes the current sweep runner.

| ID | Requirement | Today |
|---|---|---|
| SD-01 | Capability detection per model: MTP present, compatible draft models, runtime version. An unsupported combination is a reasoned "skipped" result, not a failure | missing |
| SD-02 | Every speculative configuration is linked to an "off" measurement with the same model, quantization, context, offload and sampling; the order alternates | partly: baseline configurations exist, without a link; fixed order |
| SD-03 | Configuration space from the grid: method, draft model and its quantization, maximum and minimum draft tokens, probability threshold, draft offload. Maximum draft tokens first coarse (1, 3, 6), then refined around the best | partly: the grid is extensible, the loader always switches speculation off |
| SD-04 | Metrics: decode speed, time to first token, total time, peak VRAM and RAM, load time, draft counters, gain over the baseline. A missing value is "n/a", never an estimate | partly: no draft counters, total time per generation, RAM or gain |
| SD-05 | Two separate fields: acceptance rate (accepted / generated draft tokens) and draft share (accepted draft tokens / output tokens) | missing |
| SD-06 | Workload profiles with results per profile: code generation, editing existing text or code, math and reasoning, prose, agent and JSON output, long context. The current repetitive synthetic prompt is likely to overstate acceptance | missing |
| SD-07 | Warm-up, at least 3 repeats, median and spread; temperature 0 and a fixed seed for speed, plus one run with production sampling; logged application and runtime versions, model file hash, load configuration | partly: no production sampling run or file hash; the application version is recorded |
| SD-08 | The requested mode is verified to be active (draft counters, log) and verified to be inactive for the baseline; otherwise the measurement is invalid | partly: the applied load configuration is compared, activity is not |
| SD-09 | Quality guard: with greedy sampling compare the output with the baseline and report the first difference (a difference alone is not an error) | missing: outputs are not stored |
| SD-10 | Basic measurement with one parallel prediction; higher concurrency as a separate dimension; compatibility checked separately for vision models | partly: one parallel prediction only |
| SD-11 | A load error, out of memory or timeout is recorded as a result and the sweep goes on | partly: it does, but two consecutive timeouts abort the run |
| SD-12 | Recommendation per model and profile with gain and memory cost; "off" if the gain is below an adjustable threshold (start: 1.10x) | partly: the evaluation recommends, without a threshold |
| SD-13 | Result format independent of the backend (backend and runtime fields) | missing |

Depends on the fixed task set (task 20) for the workload profiles. The 8 GB development GPU leaves little room for a
draft model; models that fit with headroom come first.
