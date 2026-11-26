# Requirements and planned work

[Magyar](requirements.hu.md)

What the planned parts have to do. Task numbers refer to the [roadmap](roadmap.md), which also holds the statuses.

## 1. Interface

- Start, pause, resume, stop; live status.
- Views: Pareto scatter plot (VRAM vs speed, point size = context length), model × test suite heatmap, radar chart for
  2–4 models, filterable table with Excel export.
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

### Interface to the core (decided 2026-11-26, not implemented)

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

The headless assistant beta API of the LM Studio Bionic application (listed in the 1.2.1 release notes) is not used in
M1; the installed version is 1.2.0.

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

### Phase 0 trial plan (agreed 2026-11-26, not run)

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
