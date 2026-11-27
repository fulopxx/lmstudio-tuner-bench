# Roadmap and decisions

[Magyar](roadmap.hu.md)

Last updated: 2026-11-27. Goal: tune and compare downloaded local models on your own hardware, for your own use cases,
using LM Studio.

Related documents: [requirements](requirements.md) (interface, testing, agent harness, speculative decoding, bias investigation, task sets, core and result format, control interface) and
[measurement findings](findings.md).

## 1. Tasks

Status: ✅ **done** (verified by running), 🟡 **partial**, 🔵 **in progress**, ⚪ **open**.

| # | Task | Status |
|---|---|---|
| 1 | Speed and memory tuning (context, GPU offload, flash attention, batch, KV quantization, threads) | 🟡 partial (clean sweeps of 2026-11-26 evaluated and recommended settings recorded; open: cases near the VRAM limit, filled context, quality effect of KV quantization, presets; see [findings](findings.md)) |
| 2 | Smoke test | ✅ done |
| 3 | Live status, pause, stop, resume from a given step | 🟡 partial (see section 4) |
| 4 | Selectable models, handling of new downloads (model registry, auto discovery) | 🟡 partial (model registry with `bench models` and new-download detection, 2026-11-27; picking up new models automatically during a run open) |
| 5 | Test suite filtering by model capability (e.g. image captioning only on vision models) | 🟡 partial (`--where` capability filter for runs, 2026-11-27; test suites that declare the capabilities they need open, see requirements TS-01) |
| 6 | Quality suites: coding; git handling; Hungarian language; image recognition and captioning; decisions and explanations based on application screenshots; game and 3D design (Unreal, Blender); cybersecurity | ⚪ open |
| 7 | MCP / tool use: format, tool selection, parameters, result handling, multi-step chains, parallel calls; instruction following at three levels of detail (goal, numbered steps, one step at a time) | 🟡 partial (M1 task set, measured live on four models: tool selection, arguments, error and result handling, chains of up to four steps, tasks that need no tool; open: parallel calls, the three instruction levels, a real MCP server) |
| 8 | Tool timeout behaviour as a **model capability**: no endless retrying, stops after a limit and tells the user | 🟡 partial (M1 tasks with a tool timeout and a transient error: whether the model reports the problem or retries; endless retrying shows as `loop`; a limit set by the model itself is not measured) |
| 9 | Skill use: picking the right skill, following its steps and prohibitions | ⚪ open |
| 10 | Narrowly scoped frontier-model grading in the final round | ⚪ open (decision pending) |
| 11 | Web UI and dashboard; a simple Excel evaluation sheet with Excel charts | ⚪ open |
| 12 | Show and measure the browser's GPU usage | ⚪ open |
| 13 | Project shareable on git | ✅ done (public on GitHub since 2026-11-27) |
| 14 | Secondary NiceGUI control panel | ⚪ open, low priority |
| 15 | Bilingual (English primary, Hungarian) documentation and UI with language switching | 🟡 partial (documents done, no UI yet) |
| 16 | Agent harness: a small tool loop (files, search, git, shell) in a sandbox, with interruption, recovery and context handling (see [requirements](requirements.md), section 3) | 🟡 partial (M1 harness: file read and mock tools, limits, stop, trace; search, git, shell, recovery and context handling open) |
| 17 | Failure analysis: full trace per run, FMEA-style failure taxonomy, trace-based diagnostics, report per model (see [requirements](requirements.md), section 3) | 🟡 partial (taxonomy v2, rule-based categorizer with evidence, per-model report with intervals, manual review done; open: transition graph, value provenance, LLM judge) |
| 18 | Try the official LM Studio SDK on the installed version; if it works, replace the config file edits with it | ✅ done |
| 19 | Model-specific tool-call differences and repair methods (retry, schema constraint, grammar) | ⚪ open |
| 20 | Fixed, reproducible evaluation task set with pass/fail checks and repeated runs | ✅ done (M1 task set, 2026-11-27: 20 tasks with reference solutions, repeated runs; further sets come with task 6) |
| 21 | Interrupt and recovery tests: stop during a tool call, truncated output, resume | ⚪ open |
| 22 | Context management measurements: truncation, summarization, tool result size limits, behaviour as context grows | ⚪ open |
| 23 | Investigation: is a model biased? Factors, test prompts, per-model measurement (see [requirements](requirements.md), section 4) | ⚪ open (not examined yet) |
| 24 | Speculative decoding as an optimization dimension: draft model and MTP compared with speculation off, per task type (see [requirements](requirements.md), section 5) | 🔵 in progress (phase 0 done; phase 1 open) |
| 25 | Requirement traceability: tests name the requirement IDs they cover; a script builds the matrix (requirement → tests → offline, live, not covered) and fails on unknown IDs or on IDs that differ between the languages | ⚪ open |
| 26 | Requirement quality: review the existing requirements against the writing rules of the [requirements](requirements.md) and add the verification column | ⚪ open |
| 27 | Statistical comparison of models: task-level intervals (bootstrap over tasks), paired per-task differences with a "practically equivalent" result, `pass@k`, and a "run more?" advisor that estimates the run time and says whether more repeats or more tasks would narrow the result. The Wilson interval treats attempts as independent; on the ten-repeat M1 run the task-level intervals were about twice as wide (2026-11-27, [findings](findings.md)) | ⚪ open (after the public release) |
| 28 | Read-only MCP server over the measurement results: a thin layer over the core, every tool matching a CLI command; stdio transport first, tried with the MCP Inspector. The SDK version is checked before adoption and installed by the owner with a pinned version. Mock tools served over MCP belong to task 7 | ⚪ open (after the public release) |
| K | **Separate task:** porting agent skills (e.g. session export) so that they work compatibly in LM Studio | ⚪ open (not examined yet) |

### Planned improvements

- Result format: schema version and hardware fingerprint (GPU, driver, LM Studio and runtime version).
- Recommended preset per model, compared with the current LM Studio settings. Applied only after confirmation.
- Later: tuning of sampling parameters.
- After M1 (task 17): an aggregated tool transition graph over many attempts (edge weight = frequency; loops and
  departures from the correct chain), filterable by model, task and category, exported by the core as DOT.

## 2. Order of work

### Milestone M1: first public release

M1 comes first: one thin slice that works end to end. The A–L table below applies to the work after it.

| M1 step | Content | Status |
|---|---|---|
| 1 | SDK trial on the installed LM Studio (task 18) | ✅ done |
| 2 | Clean sweep, evaluation, recommended settings per model | ✅ done |
| 3 | Repository preparation, license, public release | ✅ done (2026-11-27: checks for secrets, personal data and paths including the git history, install from a fresh clone, public repository, release `v0.1.0`) |
| 4 | Minimal TypeScript harness: 1–2 tools (file read and mock, no shell), timeout, interrupt, trace | ✅ done (2026-11-26: `bench agent run`, 4/4 example tasks live on one model; Ctrl+C stop tested offline only) |
| 5 | 10–20 fixed tasks, repeated runs, failure category report | ✅ done (2026-11-27: task set, report, live runs with 4 models × 20 tasks × 5 and × 10, manual review of the failures, taxonomy v2) |
| 6 | Result table in the README | ✅ done (2026-11-27, ten-repeat M1 run) |

After M1: web dashboard, quality suites, context management measurements, NiceGUI.

### Full order

| Step | Content | Status |
|---|---|---|
| A | Evaluate the trial sweep, final round | ✅ done (trial and clean sweeps evaluated) |
| B | Repository preparation, English and Hungarian documents | ✅ done (bilingual documents; public since 2026-11-27) |
| C | Split core and CLI, versioned result format, model registry | ✅ done (2026-11-27: [requirements](requirements.md), section 7: C1 package layout, C2 core functions, C3 result format and machine settings, C4 model registry) |
| D | Finalize `docs/architecture.md`: data formats, control interface | ✅ done (2026-11-27: [architecture](architecture.md), section 10, control interface and data formats; [requirements](requirements.md), section 8) |
| D2 | Control interface in the core and the CLI ([requirements](requirements.md), section 8, IF-01 to IF-23), before E | 🔵 in progress (D2a done 2026-11-27 with offline tests: `bench/core/runstate.py`, `state/runs/<id>/` for sweep and agent runs, lock `state/active.json`; live check pending. Plan agreed 2026-11-27: D2a state per run and one GPU run at a time, IF-10, IF-11, IF-13; D2b progress log, request source, agent stop through the control file, IF-12, IF-14, IF-15; D2c `--json`, IF-01; D2d `bench check`, `bench runs`, `bench close` (the state machine change shown to the owner first), IF-20 to IF-22; D2e schema versions, IF-23. The API requirements IF-02 to IF-04 come with the API) |
| E | HTML dashboard and Excel export (after D) | ⚪ open |
| F | Web control UI | ⚪ open |
| G | Agent harness: tool loop, sandbox, trace log, CLI | 🟡 partial (M1 harness: tool loop, sandbox, trace, `bench agent`; search, git and shell tools open) |
| H | Tool calling, timeout and instruction following suite, running on the harness | 🟡 partial (tool calling and timeout in the M1 task set; instruction following open) |
| I | Failure analysis: categories and per-model report | ✅ done (taxonomy v2 and per-model report, 2026-11-27) |
| J | Quality suites | ⚪ open |
| L | Secondary NiceGUI panel (low priority) | ⚪ open (low priority) |
| K | Skill porting (separate task) | ⚪ open (separate task) |

E–F and G–J can proceed in parallel. **Designing** the web UI (views, wireframes) without code can start earlier.

Task 24 (speculative decoding): the short trial (phase 0) comes before M1 step 4, the integration after M1 together
with step C.

## 3. Decisions

### Measurement and runner

| Topic | Decision |
|---|---|
| Per-model LM Studio config files | Not edited; the runner loads through the SDK |
| LM Studio access | Official TypeScript SDK for loading (verified); CPU threads through the llama.cpp argument override; used by the sweep runner |
| Error handling | Failed steps are not retried automatically; abort after two consecutive timeouts; pause when the GPU is busy, re-check every 90 s and continue by itself (a manual pause stays) |
| Statistics | Median and spread, Pareto front, adjustable weighted score, bootstrap confidence intervals; Elo / Bradley–Terry for pairwise grading. No ML/DL needed |
| Speculative decoding switch | Only at load, through the SDK load fields (`speculativeDraftMtp`; `speculativeDraftSimple` with `speculativeDraftModel`); measured over REST, which returns the draft counters (phase 0, 2026-11-26) |
| Speculative decoding | Speculation off stays the baseline and may be the recommendation; LM Studio only for now, a second backend (`llama-server`) is decided later if results justify it |

### Architecture and interfaces

| Topic | Decision |
|---|---|
| CLI parity | The terminal version comes first: it must be able to do everything, graphical interfaces cannot do more. New features appear in the core and CLI first |
| GUI layer | A thin layer over the core, without its own measurement or evaluation logic; the data behind charts is also available from the CLI. A test checks that every API operation has a CLI counterpart |
| Frontend | React + Vite + TypeScript, Mantine, Apache ECharts |
| Backend | FastAPI, `127.0.0.1` only |
| Web development | Starts after step D and lives in the `web/` folder; the core interface is agreed first |
| Agent harness | Own module with failure analysis, written in TypeScript from the start. The first version has no shell tool |
| Harness interface | One harness process per model and task set, JSON spec on stdin, `RESULT:` summary, JSONL trace; checks and categories in the core; own tool loop with an SDK and a scripted backend (2026-11-26; [requirements](requirements.md), section 3) |
| Agent result views | The core produces the tables and graph models, the CLI exports them (JSON; DOT when the first graph view is built); interfaces only draw. No third interface (no tkinter). A graph library (`networkx`) or the Graphviz binary only by a separate decision, when a graph algorithm is needed (2026-11-26) |

### Language and documentation

| Topic | Decision |
|---|---|
| Language | English is primary; everything also gets a Hungarian version (documents, README, UI). The English README links to the Hungarian one |
| File naming | `name.md` is English, `name.hu.md` is Hungarian; PDFs follow the same pattern |
| Hungarian wording | Technical terms that are commonly used in English, or lack a good Hungarian equivalent, stay in English, especially in the UI |
| Code | Code and comments in English |

### Project

| Topic | Decision |
|---|---|
| Focus | Failure taxonomy and trace-based diagnostics are what sets the project apart; speed benchmarking is the base |
| License | MIT |

## 4. Open technical items

### Measurement

| Item | Current knowledge | Status |
|---|---|---|
| Spill into shared GPU memory | The `near_vram_limit` flag is not enough (in the clean sweep a slow configuration stayed below its threshold). The `spill?` flag of the evaluation infers it from speed; shared GPU memory is not measured | ⚪ open |
| Filled context | The sweeps have no prompts that actually fill the context | ⚪ open |
| Background VRAM use | Speed measurements are only valid on an idle GPU. A way to hold or record the background use when comparing configurations near the VRAM limit is missing | ⚪ open |
| CLI `lms load` | Its relation to the per-model default config values has not been measured | ⚪ open |
| Speculative decoding | Phase 0 trial done on 2026-11-26 ([requirements](requirements.md), section 5): switched at load only, counters in the SDK and REST. Open for phase 1: compatibility check of draft pairs, max draft tokens, why greedy outputs differ from the baseline | ⚪ open |
| Value provenance in agent traces | A graph of where each argument and answer value comes from (prompt, earlier tool results) could replace the text search behind `wrong_arguments/invented_value` and show how a tool error reaches the answer. Defining the edges is uncertain, since models rephrase values; to be tried after M1 | ⚪ open |
| LLM judge for the heuristic rules | Keyword lists are never complete: the first live M1 run showed four gaps (2026-11-27). Proposal for after M1, next to task 10: a second opinion only for the heuristic decisions (did the answer report the error or the limit, did it invent a value), with a written scoring rubric and a judge model other than the measured one, run offline after a run. The rule stays the primary decision; the report shows where judge and rule disagree, and only those cases go to manual review. Before use, the judge is calibrated against manual labels (agreement such as Cohen's kappa); its own bias is a known risk | ⚪ open |
| Sampling profile patterns | The Qwen3 pattern of `configs/sampling.json` misses decimal sizes (`qwen3-1.7b` got the fallback profile in a live run, 2026-11-27) and would give the non-thinking `Qwen3-4B-Instruct-2507` the thinking profile. Fix after the downloads: profiles from the model cards, and a test of model key → profile | ✅ done (2026-11-27: decimal sizes match, a profile for `Qwen3-4B-Instruct-2507` from its card, a test of model key → profile; the 0.5B coder card names repeat penalty 1.05 against 1.1 of the 7B, kept at 1.1 because the 0.5B serves as a draft model) |
| Model registry: new models by date | Two snapshots make "new" disappear at the next refresh. Proposal (2026-11-27): a `first_seen` date per model instead of the previous snapshot, `bench models list --new` and `--refresh` instead of `bench models new`, a refresh before runs with `--where` when LM Studio is reachable (stored snapshot and a warning otherwise); `refresh` stays a separate writing operation for the API | ✅ done (2026-11-27: `first_seen` per model, `bench models list --new` and `--refresh`, refresh before runs with `--where`) |

### Stability and testing

| Item | Current knowledge | Status |
|---|---|---|
| Not tried live (sweep) | `stop --now`; automatic pause on a busy GPU and the automatic resume after it (offline tests only); a connection breaking during generation (offline tests only); Ctrl+C; load timeout; `--redo-failed`; the warning for a runtime without GPU support. Resume after a reboot was used once on 2026-11-26; a `configs/machine.local.json` with LM Studio in another folder (offline tests only). Step D2a (offline tests only): per-run state files and the GPU lock in a real sweep and agent run, an agent run refused during a sweep (in `tests/live_control_test.py`) and the reverse, a stale lock after a killed run | ⚪ open |
| Not tried live (agent harness) | Stop of a real run: Ctrl+C or the stop command, the second Ctrl+C that kills the harness and the trace it leaves; `--run-timeout`; attempt time limit with a real model; a tool call the SDK reports as unparsable (`onToolCallRequestFailure`, never seen); removal of a `bench-agent` instance left over from a killed run; a context other than 8192; a real model trying to read outside the sandbox. All but the last three are covered by offline tests. New in step 5a, offline only: mock answers by call count (`sequence`); the rebuild of attempts from traces after a killed harness; a real context overflow stopped by `stopAtLimit`. Tried live on 2026-11-27: the sampling profile and `stopAtLimit` are applied (LM Studio reports them back, recorded in the trace), and the categorizer on real runs; tried live on 2026-11-27: `--models` with four models, the M1 task set, `report` and `show` on a real run; `--repeats` 5 and 10 with the profile temperatures, and the round limit with the final round without tools | ⚪ open |
| Late heartbeat | During the sweeps of 2026-11-26 `status --watch` reported "process gone" several times although the run went on. The view no longer ends on a late heartbeat of a living process; why the heartbeat was late is unknown (not reproduced) | 🟡 partial |
| Display freeze | Once during those sweeps the display stopped responding (Windows reported `explorer.exe` waiting on `dwm.exe`) while the runner was still writing its heartbeat; the machine had to be reset and `resume` continued the run. No display driver reset or hardware error was logged; the cause is unknown | ⚪ open |
| Tests without the harness dependencies | In a fresh clone without the harness packages, three Python tests that start the harness failed with a broken pipe. Fixed on 2026-11-27: they are skipped with a message, `bench agent run` stops with the install command, and the README has an install section for a fresh clone (checked in a fresh clone with and without the packages) | ✅ done |
| LM Studio internal path repeated | The path of the internal LM Studio files (`~\.lmstudio\...`, `lms.exe`) is built separately in six TypeScript files; the Python code reads it from one module since step C3 (CR-15). A shared setting for the TypeScript probes would make other installations easier. After the public release | ⚪ open |

### Dependencies

Dependency advisory in `harness/`: `npm audit` reports
[GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) (memory exhaustion in `zod` below 4.6.6),
pulled in by `@lmstudio/sdk` 2.1.0, which requires `zod ^3.22.4`. Assessed as low risk for local use (availability
only; input comes from the local server and from model output, so limit tool argument sizes). Do not run
`npm audit fix --force` (it downgrades the SDK) and do not force zod 4 (reported to break the SDK). Already raised
upstream in [lmstudio-js issue 362](https://github.com/lmstudio-ai/lmstudio-js/issues/362); check again on every SDK
update.
