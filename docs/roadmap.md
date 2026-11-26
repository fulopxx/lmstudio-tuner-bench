# Roadmap and decisions

[Magyar](roadmap.hu.md)

Last updated: 2026-11-26. Goal: tune and compare downloaded local models on your own hardware, for your own use cases,
using LM Studio.

## 1. Tasks

Status: **done** (verified by running), **partial**, **in progress**, **open**.

| # | Task | Status |
|---|---|---|
| 1 | Speed and memory tuning (context, GPU offload, flash attention, batch, KV quantization, threads) | partial (trial sweep 56/56 finished and evaluated with `bench evaluate`; clean sweep pending, numbers not final) |
| 2 | Smoke test | done |
| 3 | Live status, pause, stop, resume from a given step | partial (see section 6) |
| 4 | Selectable models, handling of new downloads (model registry, auto discovery) | partial (manual list in the grid file) |
| 5 | Test suite filtering by model capability (e.g. image captioning only on vision models) | open |
| 6 | Quality suites: coding; git handling; Hungarian language; image recognition and captioning; decisions and explanations based on application screenshots; game and 3D design (Unreal, Blender); cybersecurity | open |
| 7 | MCP / tool use: format, tool selection, parameters, result handling, multi-step chains, parallel calls; instruction following at three levels of detail (goal, numbered steps, one step at a time) | partial (a single tool probe in the smoke test) |
| 8 | Tool timeout behaviour as a **model capability**: no endless retrying, stops after a limit and tells the user | open (only the harness's own timeouts exist) |
| 9 | Skill use: picking the right skill, following its steps and prohibitions | open |
| 10 | Narrowly scoped frontier-model grading in the final round | open (decision pending) |
| 11 | Web UI and dashboard; a simple Excel evaluation sheet with Excel charts | open |
| 12 | Show and measure the browser's GPU usage | open |
| 13 | Project shareable on git | partial (not released yet) |
| 14 | Secondary NiceGUI control panel | open, low priority |
| 15 | Bilingual (English primary, Hungarian) documentation and UI with language switching | partial (documents done, no UI yet) |
| 16 | Agent harness: a small tool loop (files, search, git, shell) in a sandbox, with interruption, recovery and context handling (see section 7) | open |
| 17 | Failure analysis: full trace per run, FMEA-style failure taxonomy, trace-based diagnostics, report per model (see section 7) | open |
| 18 | Try the official LM Studio SDK on the installed version; if it works, replace the config file edits with it | partial (SDK verified; the sweep runner still edits config files) |
| 19 | Model-specific tool-call differences and repair methods (retry, schema constraint, grammar) | open |
| 20 | Fixed, reproducible evaluation task set with pass/fail checks and repeated runs | open |
| 21 | Interrupt and recovery tests: stop during a tool call, truncated output, resume | open |
| 22 | Context management measurements: truncation, summarization, tool result size limits, behaviour as context grows | open |
| K | **Separate task:** porting agent skills (e.g. session export) so that they work compatibly in LM Studio | open (not examined yet) |

### Planned improvements

- Result format: schema version and hardware fingerprint (GPU, driver, LM Studio and runtime version).
- Final round: more repetitions; separate the effect of context length from KV quantization.
- Recommended preset per model, compared with the current LM Studio settings. Applied only after confirmation.
- Later: tuning of speculative decoding and sampling parameters.

## 2. Order of work

### Milestone M1: first public release

M1 comes first: one thin slice that works end to end. The A–L table below applies to the work after it.

| M1 step | Content | Status |
|---|---|---|
| 1 | SDK trial on the installed LM Studio (task 18) | done |
| 2 | Clean sweep, evaluation, recommended settings per model | in progress |
| 3 | Repository preparation, license, public release | in progress |
| 4 | Minimal TypeScript harness: 1–2 tools (file read and mock, no shell), timeout, interrupt, trace | open |
| 5 | 10–20 fixed tasks, repeated runs, failure category report | open |
| 6 | Result table in the README | open |

After M1: web dashboard, quality suites, context management measurements, NiceGUI.

### Full order

| Step | Content | Status |
|---|---|---|
| A | Evaluate the trial sweep, final round | partial (trial sweep evaluated; final round pending) |
| B | Repository preparation, English and Hungarian documents | partial (bilingual documents done; public release pending) |
| C | Split core and CLI, versioned result format, model registry | open |
| D | Finalize `docs/architecture.md`: data formats, control interface | partial (draft exists) |
| E | HTML dashboard and Excel export (after D) | open |
| F | Web control UI | open |
| G | Agent harness: tool loop, sandbox, trace log, CLI | open |
| H | Tool calling, timeout and instruction following suite, running on the harness | open |
| I | Failure analysis: categories and per-model report | open |
| J | Quality suites | open |
| L | Secondary NiceGUI panel (low priority) | open (low priority) |
| K | Skill porting (separate task) | open (separate task) |

E–F and G–J can proceed in parallel. **Designing** the web UI (views, wireframes) without code can start earlier.

## 3. Decisions

| Topic | Decision |
|---|---|
| Per-model LM Studio config files | The benchmark may edit them temporarily, with backup and restore |
| Error handling | No automatic retries; abort after two consecutive timeouts; pause when the GPU is busy |
| Frontend | React + Vite + TypeScript, Mantine, Apache ECharts |
| Backend | FastAPI, `127.0.0.1` only |
| Statistics | Median and spread, Pareto front, adjustable weighted score, bootstrap confidence intervals; Elo / Bradley–Terry for pairwise grading. No ML/DL needed |
| Language | English is primary; everything also gets a Hungarian version (documents, README, UI). The English README links to the Hungarian one |
| File naming | `name.md` is English, `name.hu.md` is Hungarian; PDFs follow the same pattern |
| Hungarian wording | Technical terms that are commonly used in English, or lack a good Hungarian equivalent, stay in English, especially in the UI |
| Code | Code and comments in English |
| Agent harness | Own module with failure analysis, written in TypeScript from the start. The first version has no shell tool |
| LM Studio access | Official TypeScript SDK for loading (verified); CPU threads through the llama.cpp argument override; config file edits to be removed when the sweep runner is switched over |
| Focus | Failure taxonomy and trace-based diagnostics are what sets the project apart; speed benchmarking is the base |
| License | MIT |
| CLI parity | The terminal version comes first: it must be able to do everything, graphical interfaces cannot do more. New features appear in the core and CLI first |
| GUI layer | A thin layer over the core, without its own measurement or evaluation logic; the data behind charts is also available from the CLI. A test checks that every API operation has a CLI counterpart |
| Web development | Starts after step D and lives in the `web/` folder; the core interface is agreed first |

## 4. UI requirements

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

## 5. Testing (planned)

- Python logic and FastAPI: `pytest` (it can run the existing `unittest` tests).
- React components: Vitest + React Testing Library.
- End to end: Playwright, with a fake runner and recorded sample results, without a GPU. Not run during measurements.
- Live GPU tests are separate and started manually (`tests\live_control_test.py`).

## 6. Open technical items

- The 56-job run of 2026-11-26 is a trial run: other programs may have been using the CPU, its numbers are not final. A
  clean full sweep follows later on an idle machine.
- Not tried live: `stop --now`, automatic pause on a busy GPU, Ctrl+C, resume after a reboot, load timeout,
  `--redo-failed`.
- Detecting spill into shared GPU memory: the current `near_vram_limit` flag is probably not enough (partial results of
  the trial sweep show a slowdown it did not flag; the cause is not verified yet).
- The relation between CLI `lms load` and the per-model default config values has not been measured.
- Speed measurements are only valid on an idle GPU.
- For the clean sweep: finer offload steps and batch size combined with longer context for 12–14B models; separate
  context length from KV quantization; prompts that actually fill the context; at least 3 repeats; measure shared GPU
  memory instead of guessing spill from speed.

- Dependency advisory in `harness/`: `npm audit` reports
  [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) (memory exhaustion in `zod` below 4.6.6),
  pulled in by `@lmstudio/sdk` 2.1.0, which requires `zod ^3.22.4`. Assessed as low risk for local use (availability
  only; input comes from the local server and from model output, so limit tool argument sizes). Do not run
  `npm audit fix --force` (it downgrades the SDK) and do not force zod 4 (reported to break the SDK). Already raised
  upstream in [lmstudio-js issue 362](https://github.com/lmstudio-ai/lmstudio-js/issues/362); check again on every SDK
  update.

## 7. Agent harness and failure analysis: initial requirements

Draft, to be detailed before step G.

**Harness**

- Written in TypeScript, talking to LM Studio through the official SDK if the trial (task 18) succeeds.
- Runs a model in a tool loop. The first version has file reading and mock tools only (mock tools give deterministic
  tests); search, git and shell follow after the sandbox decision.
- Everything runs in a throwaway sandbox folder; no network by default.
- Limits: timeout per tool call, maximum number of steps per task, no endless retries; the user is told when a limit is hit.
- Interruption and resume; clean recovery from tool errors and invalid model output.
- Context handling: conversation history, tool results, what happens when the context fills up.
- Usable from the CLI first, like every other feature.

**Failure analysis**

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

**Open**

- Interface between the Python core and the TypeScript harness (process boundary, trace format).
- How the sandbox restricts model-generated shell commands. This must be decided before any such command is executed.
- Loading from the Python core through the SDK: a short-lived Node loader is enough (verified: the model stays
  loaded). Still open: finding LM Studio's API port without an internal file.
