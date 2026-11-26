# Roadmap and decisions

[Magyar](roadmap.hu.md)

Last updated: 2026-11-26. Goal: tune and compare downloaded local models on your own hardware, for your own use cases,
using LM Studio.

Related documents: [requirements](requirements.md) (interface, testing, agent harness, speculative decoding, bias investigation) and
[measurement findings](findings.md).

## 1. Tasks

Status: ✅ **done** (verified by running), 🟡 **partial**, 🔵 **in progress**, ⚪ **open**.

| # | Task | Status |
|---|---|---|
| 1 | Speed and memory tuning (context, GPU offload, flash attention, batch, KV quantization, threads) | 🟡 partial (clean sweeps of 2026-11-26 evaluated and recommended settings recorded; open: cases near the VRAM limit, filled context, quality effect of KV quantization, presets; see [findings](findings.md)) |
| 2 | Smoke test | ✅ done |
| 3 | Live status, pause, stop, resume from a given step | 🟡 partial (see section 4) |
| 4 | Selectable models, handling of new downloads (model registry, auto discovery) | 🟡 partial (manual list in the grid file) |
| 5 | Test suite filtering by model capability (e.g. image captioning only on vision models) | ⚪ open |
| 6 | Quality suites: coding; git handling; Hungarian language; image recognition and captioning; decisions and explanations based on application screenshots; game and 3D design (Unreal, Blender); cybersecurity | ⚪ open |
| 7 | MCP / tool use: format, tool selection, parameters, result handling, multi-step chains, parallel calls; instruction following at three levels of detail (goal, numbered steps, one step at a time) | 🟡 partial (a single tool probe in the smoke test) |
| 8 | Tool timeout behaviour as a **model capability**: no endless retrying, stops after a limit and tells the user | ⚪ open (only the harness's own timeouts exist) |
| 9 | Skill use: picking the right skill, following its steps and prohibitions | ⚪ open |
| 10 | Narrowly scoped frontier-model grading in the final round | ⚪ open (decision pending) |
| 11 | Web UI and dashboard; a simple Excel evaluation sheet with Excel charts | ⚪ open |
| 12 | Show and measure the browser's GPU usage | ⚪ open |
| 13 | Project shareable on git | 🟡 partial (not released yet) |
| 14 | Secondary NiceGUI control panel | ⚪ open, low priority |
| 15 | Bilingual (English primary, Hungarian) documentation and UI with language switching | 🟡 partial (documents done, no UI yet) |
| 16 | Agent harness: a small tool loop (files, search, git, shell) in a sandbox, with interruption, recovery and context handling (see [requirements](requirements.md), section 3) | ⚪ open |
| 17 | Failure analysis: full trace per run, FMEA-style failure taxonomy, trace-based diagnostics, report per model (see [requirements](requirements.md), section 3) | ⚪ open |
| 18 | Try the official LM Studio SDK on the installed version; if it works, replace the config file edits with it | ✅ done |
| 19 | Model-specific tool-call differences and repair methods (retry, schema constraint, grammar) | ⚪ open |
| 20 | Fixed, reproducible evaluation task set with pass/fail checks and repeated runs | ⚪ open |
| 21 | Interrupt and recovery tests: stop during a tool call, truncated output, resume | ⚪ open |
| 22 | Context management measurements: truncation, summarization, tool result size limits, behaviour as context grows | ⚪ open |
| 23 | Investigation: is a model biased? Factors, test prompts, per-model measurement (see [requirements](requirements.md), section 4) | ⚪ open (not examined yet) |
| 24 | Speculative decoding as an optimization dimension: draft model and MTP compared with speculation off, per task type (see [requirements](requirements.md), section 5) | ⚪ open |
| K | **Separate task:** porting agent skills (e.g. session export) so that they work compatibly in LM Studio | ⚪ open (not examined yet) |

### Planned improvements

- Result format: schema version and hardware fingerprint (GPU, driver, LM Studio and runtime version).
- Recommended preset per model, compared with the current LM Studio settings. Applied only after confirmation.
- Later: tuning of sampling parameters.

## 2. Order of work

### Milestone M1: first public release

M1 comes first: one thin slice that works end to end. The A–L table below applies to the work after it.

| M1 step | Content | Status |
|---|---|---|
| 1 | SDK trial on the installed LM Studio (task 18) | ✅ done |
| 2 | Clean sweep, evaluation, recommended settings per model | ✅ done |
| 3 | Repository preparation, license, public release | 🔵 in progress |
| 4 | Minimal TypeScript harness: 1–2 tools (file read and mock, no shell), timeout, interrupt, trace | ⚪ open |
| 5 | 10–20 fixed tasks, repeated runs, failure category report | ⚪ open |
| 6 | Result table in the README | ⚪ open |

After M1: web dashboard, quality suites, context management measurements, NiceGUI.

### Full order

| Step | Content | Status |
|---|---|---|
| A | Evaluate the trial sweep, final round | ✅ done (trial and clean sweeps evaluated) |
| B | Repository preparation, English and Hungarian documents | 🟡 partial (bilingual documents done; public release pending) |
| C | Split core and CLI, versioned result format, model registry | ⚪ open |
| D | Finalize `docs/architecture.md`: data formats, control interface | 🟡 partial (draft exists) |
| E | HTML dashboard and Excel export (after D) | ⚪ open |
| F | Web control UI | ⚪ open |
| G | Agent harness: tool loop, sandbox, trace log, CLI | ⚪ open |
| H | Tool calling, timeout and instruction following suite, running on the harness | ⚪ open |
| I | Failure analysis: categories and per-model report | ⚪ open |
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
| Speculative decoding | The installed SDK has load settings for draft model and MTP and draft statistics ([requirements](requirements.md), section 5); neither their effect nor their memory cost has been tried | ⚪ open |

### Stability and testing

| Item | Current knowledge | Status |
|---|---|---|
| Not tried live | `stop --now`; automatic pause on a busy GPU and the automatic resume after it (offline tests only); a connection breaking during generation (offline tests only); Ctrl+C; load timeout; `--redo-failed`. Resume after a reboot was used once on 2026-11-26 | ⚪ open |
| Late heartbeat | During the sweeps of 2026-11-26 `status --watch` reported "process gone" several times although the run went on. The view no longer ends on a late heartbeat of a living process; why the heartbeat was late is unknown (not reproduced) | 🟡 partial |
| Display freeze | Once during those sweeps the display stopped responding (Windows reported `explorer.exe` waiting on `dwm.exe`) while the runner was still writing its heartbeat; the machine had to be reset and `resume` continued the run. No display driver reset or hardware error was logged; the cause is unknown | ⚪ open |

### Dependencies

Dependency advisory in `harness/`: `npm audit` reports
[GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) (memory exhaustion in `zod` below 4.6.6),
pulled in by `@lmstudio/sdk` 2.1.0, which requires `zod ^3.22.4`. Assessed as low risk for local use (availability
only; input comes from the local server and from model output, so limit tool argument sizes). Do not run
`npm audit fix --force` (it downgrades the SDK) and do not force zod 4 (reported to break the SDK). Already raised
upstream in [lmstudio-js issue 362](https://github.com/lmstudio-ai/lmstudio-js/issues/362); check again on every SDK
update.
