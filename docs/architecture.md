# Architecture

[Magyar](architecture.hu.md)

Last updated: 2026-11-26. **Status: draft** (to be finalized in roadmap step D). The "current" parts describe the
existing code; the "target" and "planned" parts are not implemented yet. Task list: `docs/roadmap.md`.

## 1. Principles

- **CLI parity:** the web UI and any other graphical interface cannot do more than the CLI. New features appear in the
  core and CLI first.
- **Thin interfaces:** measurement, state handling, evaluation and computation (e.g. Pareto front, scores) live in the core.
- **Few dependencies:** the Python code uses only the standard library. Models are loaded through a TypeScript helper, so
  a sweep also needs Node.js and the official LM Studio SDK. Further external packages are allowed for interfaces,
  exports and the harness.
- **Safe runs:** every external step has a timeout; failed steps are not retried automatically; pause when the GPU is
  busy, with periodic re-checks; only the model loaded by the run is unloaded; LM Studio's settings files are not
  modified.
- **Local:** the web server (planned) listens on `127.0.0.1` only.
- **Bilingual (planned):** English is primary, Hungarian is a full second language. UI texts come from language files
  (no hard-coded strings) and the language is switchable. Code, comments, identifiers and data field names are English
  and are not translated.

## 2. Current structure

| File | Role |
|---|---|
| `bench.cmd` | Short command for the sweep runner |
| `runner/sweep.py` | CLI, runner, status and control handling, table report (single file) |
| `runner/evaluate.py` | Evaluation of sweep results: estimated response time, warnings, recommendations |
| `runner/smoke.py` | Shared helpers used by the runner (commands, HTTP, streamed measurement, VRAM sampling) and a stand-alone smoke test |
| `harness/load-model.ts` | Loads one model through the SDK and exits; called by the runner |
| `harness/load-config.ts` | Mapping of sweep settings to the SDK load config, with a check of the applied values |
| `harness/load-config.test.ts` | Offline test of that mapping |
| `harness/sdk-probe.ts` | Probe of the official SDK: applied settings, VRAM and speed |
| `harness/sdk-persist.ts` | Probe: a model stays loaded after the loading process exits |
| `harness/package.json` | Node.js version requirement and the pinned SDK version |
| `configs/*.json` | Measurement grids (section 4.1) |
| `tools/export_docs.py` | PDF export of the documents (English and Hungarian) |
| `tools/make_diagrams.py` | Generator of the SVG diagrams in `docs/img/` |
| `tests/` | Offline tests and one live control test that uses the GPU |

### Processes

```
bench run / resume  (runner process)
  |-- lms.exe            model list, runtime, loaded models, server, unload
  |-- node load-model.ts one short-lived process per load, LM Studio SDK
  |-- HTTP server        generation and measurement (REST, streamed)
  |-- nvidia-smi         VRAM, GPU utilization, driver
bench status / pause / resume / stop  (separate processes, talk to the runner through files)
```

### One job

At the start of a run or resume (and in a dry run) the runner warns if the selected GGUF runtime has no GPU support
while jobs offload to the GPU.

A job is one model with one configuration. The runner executes the jobs one after the other:

1. **Check the machine** (`checking GPU`): remove a `bench-sweep` model left over from a killed run; no other model may
   be loaded; free VRAM at least `min_free_mib`; median GPU utilization of three samples at most `max_util`. Otherwise
   the run pauses.
2. **Server:** start the LM Studio server if it is not running and read its port.
3. **Load** (`loading model`) through the helper (section 4.4). The job fails if another file was loaded or a requested
   setting is not reflected in the applied configuration.
4. Record the VRAM increase.
5. **Warm-up generation** (`warm-up generation`), discarded.
6. **Measured generations** (`measuring i/n`), `repeats` times: a synthetic prompt of `prompt_lines` lines with a unique
   first line (against prompt caching), temperature 0, seed 1, at most `gen_tokens` tokens, streamed. VRAM is sampled
   during generation. Time to first token gives the prompt speed (`prompt_tokens / ttft_s`), the following tokens the
   decode speed.
7. **Unload** the run's own model.
8. Append the result row (medians over the repeats) and rewrite the table report.

A failed or timed-out step marks the job `fail` or `timeout` and the run goes on; two consecutive timeouts abort it.

## 3. Target structure (planned)

```
bench/
  core/   environment, LM Studio client, planner, runner, result store, evaluation
  cli/    commands; every feature is reachable here
  api/    FastAPI, a thin wrapper around the core
harness/  TypeScript: model loader, agent tool loop, sandbox, tools, trace log
web/      React + Vite + TypeScript, Mantine, ECharts
```

The agent harness runs tasks against a loaded model and writes a trace; failure analysis in the core turns traces into
categories and reports. Its interface to the core (process boundary and trace format) is to be defined before roadmap
step G. Requirements: `docs/requirements.md`, section 3.

```
core  ->  CLI
core  ->  FastAPI  ->  React
core  ->  NiceGUI (low priority)
```

## 4. Data formats and interfaces (current)

### 4.1 Grid file (input of a run)

| Key | Content |
|---|---|
| `comment` | Free text |
| `models` | List of model keys as printed by `lms ls`; `--models` overrides it |
| `defaults` | Load settings applied to every job (table below) |
| `configs` | List of configurations: `id`, optional `only_params` (model sizes such as `"12B"`, matched against the size reported by `lms ls`), and any setting that overrides the default |

| Setting | Meaning |
|---|---|
| `context_length` | Context length in tokens |
| `offload_ratio` | GPU offload, 0 (CPU only) to 1 (everything on the GPU) |
| `flash_attention` | true / false |
| `eval_batch_size`, `physical_batch_size` | Batch sizes |
| `parallel` | Maximum parallel predictions |
| `offload_kv_cache_to_gpu` | true / false |
| `unified_kv` | Unified KV cache, true / false |
| `threads` | CPU threads |
| `kv_quant` | `null` (f16) or `"q8_0"` for both K and V cache |

Speculative decoding is not a grid setting yet: the loader switches it off explicitly for every load.

Jobs are generated model by model in the order of `configs`; the job id is `<model>|<config id>` and jobs are numbered
from 1. `configs/*.local.json` files are the user's own grids and are not tracked; `bench run` uses
`configs/quick.local.json` if it exists, otherwise `configs/quick.json`.

### 4.2 Files between the processes

| File | Content |
|---|---|
| `state/status.json` | `run`, `state`, `phase`, `phase_since`, `reason`, `total`, `started`, `job_started`, `current` (`n`, `model`, `config`), `heartbeat` (written every 2 s), `pid`, `pid_created`, `warning` |
| `state/control.json` | `cmd` (`run` / `pause` / `stop`), `now`, `ts` |
| `state/latest.txt` | Id of the latest run (its start time, `YYYYMMDD_HHMMSS`) |
| `state/runs/<run>/plan.json` | `grid`, `jobs` (`n`, `id`, `model`, `config`, `settings`), `options`, `env` (`runtime`, `driver`, `loader`) |
| `results/sweep_<run>.jsonl` | One job result per line; the last line wins for a given `job_id` |
| `report/sweep_<run>.md` | Table report |
| `report/eval_<run>.md` | Evaluation report (section 4.5) |

`options` holds the run's command line settings: `repeats`, `gen_tokens`, `prompt_lines`, `load_timeout`,
`gen_timeout`, `min_free_mib`, `max_util`, `busy_retry_s`, and `allow_env_change` after a resume. A run continues with
these values; if `env` differs from the current machine it stops unless `--allow-env-change` is given.

### 4.3 Result rows

Fields of a successful row: `job_id`, `run`, `model`, `config`, `settings`, `model_path`, `runtime`, `driver`,
`loader`, `status`, `load_s`, `applied`, `loaded_path`, `app_version` (application that served the load), `vram_before_mib`, `vram_delta_mib`, `runs`, `ttft_s`,
`decode_tok_s`, `prompt_tok_s`, `vram_peak_mib`, `near_vram_limit` (peak within 250 MiB of the total), `job_s`,
`finished`. Each element of `runs` has `ttft_s`, `decode_tok_s`, `prompt_tok_s`, `prompt_tokens` and `vram_peak_mib`.

`status` is `ok`, `fail`, `timeout` or `invalidated`. A failed row has `error` and may lack the measurement fields; if
the machine was not usable it holds only `job_id`, `run`, `model`, `config`, `status` and `error`. `resume --from`
appends rows with just `job_id` and `invalidated`.

### 4.4 Loader helper

The runner starts `node load-model.ts` in `harness/` for each job.

- **Input** (JSON on standard input): `model` (file path as reported by `lms ls`), `identifier`, `settings`, `timeoutMs`.
- **Success:** the last output line is `RESULT:` followed by JSON with `path`, `identifier`, `loadSeconds`, `applied`
  (the configuration read back from LM Studio), `mismatches` and `app` (version of the serving application).
- **Failure:** non-zero exit code with the message on standard error. Nothing is retried.
- The SDK's API port is read from an internal LM Studio file; the `LMS_API_FILE` environment variable overrides its
  path. The model stays loaded after the helper exits. Details: `docs/lmstudio_load_parameters.md`.

### 4.5 Evaluation

`bench evaluate` reads a result file and works offline. Ranking metric: estimated seconds for a request,
`in_tokens / prompt_tok_s + out_tokens / decode_tok_s` (default 2000 and 500). It recommends the fastest configuration
per model and context length, and names the fastest unflagged one if the winner carries a flag. Flags are heuristics:
`spill?` (prompt speed below half of the model's best, or with full offload decode below 60 % of the best) and
`unstable` (repeats differ by more than 10 % in decode or 25 % in prompt speed). The report warns if the VRAM used
before the loads varied by more than 500 MiB.

## 5. Run states (current)

![Run state graph](img/run_states.svg)

| State | Meaning | Next |
|---|---|---|
| `starting` | Preparation | `running`, `stopped`, `aborted` |
| `running` | Measuring | `paused`, `stopped`, `done`, `aborted` |
| `paused` | Model unloaded, a server started by the run stopped | `running` (on `resume`, or by itself after a busy GPU), `stopped` |
| `stopped` | Stopped by the user (`stop` or Ctrl+C) | `resume` starts a new process |
| `done` | All jobs finished | `resume --from` / `--redo-failed` starts a new process |
| `aborted` | Error or two consecutive timeouts | `resume` starts a new process |

- **Pause and stop** take effect after the current job; with `--now` at the next checkpoint, and the interrupted job is
  measured again. A model load in progress is awaited.
- **Automatic pause** (machine not ready) re-checks every `busy_retry_s` seconds and continues by itself; a `pause`
  command turns the re-checks off.
- **Alive:** the runner counts as alive while its `heartbeat` is younger than 20 seconds, or while the process that wrote
  it still exists (same `pid` and `pid_created`, so a reused PID does not count). A late heartbeat of a living process
  is only reported as a warning. Only one run can be active.
- **Dead process:** if it ends without reaching an end state (killed, reboot), `status` shows it and `resume` starts a
  new process, which first unloads a model left over from the dead run.
- `status --watch` ends after two readings in a row without an active run.

The graph is generated by `tools/make_diagrams.py`.

## 6. Commands and planned API

The API routes are proposals and not implemented.

| CLI (current) | API (planned) |
|---|---|
| `bench run --dry-run` | `POST /plans` |
| `bench run [--grid] [--models] [--repeats] [--gen-tokens] [--prompt-lines] [--load-timeout] [--gen-timeout] [--min-free-mib] [--max-util] [--busy-retry]` | `POST /runs` |
| `bench status [--watch] [--jobs]` | `GET /runs/current`, `GET /runs/{id}/jobs` |
| `bench pause [--now]` | `POST /runs/current/pause` |
| `bench resume [--run] [--from N] [--redo-failed] [--allow-env-change]` | `POST /runs/{id}/resume` |
| `bench stop [--now]` | `POST /runs/current/stop` |
| `bench evaluate [--run] [--in-tokens] [--out-tokens]` | `GET /runs/{id}/evaluation` |

Exit codes of `run` and `resume`: 0 when the run is done or was stopped by the user, 3 when it was aborted, 2 for
unusable arguments. `bench <command> --help` lists the defaults.

Other entry points: `python runner/smoke.py` (smoke test of one model: inventory, GPU check, load through the CLI,
generation, tool-call probe; writes `results/smoke_*.json` and a model list into `inventory/`),
`python tools/export_docs.py`, `python tools/make_diagrams.py`, and the probes in `harness/`.

## 7. External dependencies

| Dependency | Used for |
|---|---|
| Python (tested with 3.15.2) | runner, evaluation, tools, tests |
| Node.js 24 or newer | loader helper and harness probes |
| `@lmstudio/sdk` | loading with explicit parameters (`harness/load-model.ts`) |
| LM Studio application | has to be running |
| `lms.exe` | model list (`ls`), runtime list, loaded models (`ps`), starting and stopping the server, unloading; loading only in the smoke test |
| REST `POST /v1/chat/completions` | generation and measurement |
| `nvidia-smi` | VRAM, GPU utilization, driver |
| LM Studio's `http-server.json` (internal file) | API port for the SDK; details: `docs/lmstudio_load_parameters.md` |
| Microsoft Edge | PDF export of the documents only |

The runner is Windows specific (`lms.exe` path, process check).

## 8. Planned format changes

- `schema_version` in every plan and result row.
- Fuller hardware fingerprint: GPU name, total VRAM and the runtime each model actually used, in addition to the
  recorded runtime selection, driver, loader and application version.
- Test suite results (quality, tool use) next to speed measurements.
- Flag telling whether the dashboard was open during a measurement.
- Speculative decoding (task 24): grid settings, draft statistics, workload profile and backend fields.
- Model registry with capability tags.

## 9. Open questions

- Interface between the Python core and the TypeScript harness (process boundary, trace format).
- Finding the SDK's API port without an internal LM Studio file.
- Detecting spill into shared GPU memory.
- Final choice of test layers (pytest, Vitest, Playwright).
- Whether a second inference backend (`llama-server`) is needed for further speculative decoding methods.
- Location and format of the machine-specific config file.
