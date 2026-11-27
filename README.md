# lmstudio-tuner-bench

[Magyar](README.hu.md)

Measure and compare local LLMs in LM Studio on your own hardware, in two ways:

- **Load-parameter sweep:** which load settings (context, GPU offload, KV cache, batch, threads) make a model run
  fastest on your GPU without running out of memory.
- **Agent harness:** how reliably a model uses tools on fixed tasks. A harness is the program around a model that turns
  it into an agent: it gives the model tools, runs the loop (the model asks for a tool, the harness runs it and returns
  the result), enforces limits and logs every step, so failures can be analysed afterwards.

> Unofficial tool, not affiliated with the makers of LM Studio.
> Early stage: tried on a single machine only.

## Motivation

I downloaded a lot of models and then wanted to know, on my own machine, what each of them can do, what I can use it
for well, and how to run it in an optimized way. Finding that out by hand caused plenty of headaches. LM Studio can
choose load settings automatically, but I found no built-in way to measure and compare many models and settings
systematically on my own tasks, so I started building it.

## What you can do with it

Available now:

- **Speed and memory sweep.** Runs every model in a grid of load configurations, measures prompt and decode speed and
  VRAM, and survives interruptions: pause, stop, resume (also after a reboot), automatic waiting while the GPU is busy.
- **Evaluation.** Ranks the configurations of a finished sweep by estimated response time and recommends a setting per
  model and context length, with warnings for unstable or memory-starved results.
- **Agent task runs.** Runs a set of tasks on one model through the harness, with tools in a throwaway sandbox,
  limits for rounds and time, and a trace of every step. Each attempt is checked against the task's pass/fail rules,
  for example whether the right tool was called and whether the answer contains the expected facts.
- **Probes (advanced).** Small scripts that check what the installed LM Studio really supports, for example
  speculative decoding (draft models, MTP) or tool calls through the SDK.

Planned ([roadmap](docs/roadmap.md)): quality test suites
(coding, Hungarian, vision, tool use), speculative decoding as a sweep dimension and a web dashboard.

## Requirements

- Windows, NVIDIA GPU (`nvidia-smi`)
- LM Studio with the `lms` CLI (tested with 1.2.0)
- Python (tested with 3.15.2), no external packages
- Node.js 24 or newer (tested with 26.13.0) and the LM Studio SDK: run `npm.cmd ci --ignore-scripts` in `harness\`
- Microsoft Edge, only for the PDF export of the documents

**Known limitation:** models are loaded through the official LM Studio SDK, and the SDK's API port is read from an
internal LM Studio file (`~\.lmstudio\apps\bionic\.internal\http-server.json`), which may differ on other
installations (override with the `LMS_API_FILE` environment variable). The application has to be running. Details:
[load parameters](docs/lmstudio_load_parameters.md).

## Usage

In PowerShell, from the project folder.

### Install from a fresh clone

The Python part uses the standard library only, so there is no `requirements.txt` and no virtual environment to set
up. The harness packages are pinned in `harness\package-lock.json`; `npm ci` installs exactly those versions.

```powershell
git clone https://github.com/fulopxx/lmstudio-tuner-bench.git
cd lmstudio-tuner-bench
cd harness; npm.cmd ci --ignore-scripts; cd ..
python -m unittest discover -s tests
```

The last line runs the offline tests (no GPU, no LM Studio). Without the harness packages, the tests that start the
harness are skipped with a message, and `bench agent run` stops with the command to run.

### Quick start

| Command | What it does |
|---|---|
| `.\bench agent run --scripted tests\agent_scripted.json` | Runs the example agent tasks with scripted model replies: no GPU and no LM Studio needed, shows the whole path (one scripted reply fails its checks on purpose) |
| `.\bench run --dry-run` | Lists the jobs of the quick sweep without starting anything |

### Speed and memory sweep

Run the sweep in one terminal (live log) and control it from another.

| Command | What it does |
|---|---|
| `.\bench run` | Starts the quick sweep (see [Choosing models](#choosing-models)) |
| `.\bench run --models qwen3-8b,qwen2.5-coder-7b-instruct` | Only the given models |
| `.\bench run --grid configs\quick.json` | A given grid file (models and configurations), here the sample one |
| `.\bench status --watch` | Live status (refreshes every 3 s, Ctrl+C leaves the view only) |
| `.\bench status --jobs` | Every job with number and state |
| `.\bench pause` | Pause after the current job |
| `.\bench pause --now` | Pause immediately; the interrupted job will be measured again |
| `.\bench resume` | Continue (from pause, or after a stop or reboot) |
| `.\bench resume --from 12` | Measure everything again from job 12 |
| `.\bench resume --redo-failed` | Also measure failed and timed-out jobs again |
| `.\bench stop` / `.\bench stop --now` | Exit; can be resumed later |
| `.\bench evaluate` | Ranks the finished sweep by estimated response time and writes a report (offline) |
| `.\bench evaluate --in-tokens 8000 --out-tokens 300` | The same for a different input / output ratio |

Behaviour:

- On pause and stop the model is unloaded, and a server started by the tool is stopped.
- `--now` takes effect at the next checkpoint. A model load in progress is not interrupted but awaited (240 s at most).
- If the GPU is busy or someone else loaded a model, the run pauses by itself, checks again every 90 s and continues
  once the machine is free (`--busy-retry <seconds>`, `0` waits for `resume`). A pause requested with `bench pause`
  never ends by itself.
- Failed steps are never retried automatically. Two consecutive timeouts abort the run.
- If the runtime or driver version changes, the run does not continue without `--allow-env-change`.
- A warning is shown if the selected GGUF runtime has no GPU support although the grid offloads to the GPU.
- LM Studio's per-model settings files are not modified. The runner loads its model as `bench-sweep`; if a killed run
  left it loaded, the next start unloads it.

### Agent tasks

| Command | What it does |
|---|---|
| `.\bench agent run --model qwen3-8b` | Runs the example tasks (`tasks\examples.json`) on one model and checks the answers |
| `.\bench agent run --model qwen3-8b --repeats 3 --only file-marker` | Selected tasks, several attempts each |
| `.\bench agent run --model qwen3-8b --tasks <file> --context 16384` | Another task file, another context length |
| `.\bench agent run --models qwen3-8b,qwen3.5-4b-mtp --tasks tasks\m1.json` | The M1 task set (20 tasks) on several models, one after another |
| `.\bench agent report` | Report of the latest run: pass rates with intervals, failure categories, longest reliable chain (offline) |
| `.\bench agent show <run> chain-3a-2` | The steps of one attempt, with the trace event that decided its category marked (offline) |

A task file lists tasks with a prompt, the tools the model may use (`read_file`, `mock_lookup`), an optional folder of
files copied into the task's sandbox, the answers of the mock tool (result, error or delay per id) and the checks, for
example:

```json
{ "id": "file-marker", "prompt": "What is the marker written in the file notes.txt?", "fixtures": "notes",
  "tools": ["read_file", "mock_lookup"], "checks": { "tool_called": "read_file", "answer_contains": ["BLUE-HERON-17"] } }
```

Behaviour:

- The model is loaded as `bench-agent` with settings that measured well (full offload, f16 KV cache) and unloaded at
  the end. The run does not start if another model is loaded or the GPU is busy.
- Limits per attempt (adjustable in the task file): 6 tool rounds, 10 s per tool call, 180 s in total. When the round
  limit is hit, the model gets one more round without tools to answer the user.
- An unknown tool or invalid arguments go back to the model as an error. A tool call the model writes as plain text is
  not executed; it is kept in the trace.
- Ctrl+C cancels the running prediction or tool call, records the attempt as aborted and skips the remaining ones; a
  second Ctrl+C kills the harness. The model is unloaded in both cases.
- Sampling follows the model family's profile in `configs\sampling.json` (values from the model cards);
  `--temperature` overrides the temperature. Five attempts per task by default.
- Every failed attempt gets a failure category with the trace event as evidence, and is marked silent when the
  answer gives the user no sign of the problem ([failure taxonomy](docs/failure_taxonomy.md)).
- Results: one JSON line per attempt in `results\agent_<run>.jsonl`; the trace of every attempt (each prediction, tool
  call and result) and its sandbox below `results\agent\<run>\`.

### Results: M1 agent task set

20 tasks (direct and chained tool calls, argument handling, tool errors, limits, tasks that need no tool), ten
attempts each, run on 2026-11-27 with LM Studio 1.2.0 on one RTX 2070 (8 GB), context 8192, sampling per model card.
Rate with 95 % Wilson interval; pass^10 is the estimated chance that a task passes in all ten attempts, averaged over
the tasks; a chain length counts as reliable at 80 % or more. Full report: `bench agent report`.

| Model | Passed | Rate (95 % CI) | pass^10 | Silent failures | Longest reliable chain |
|---|---|---|---|---|---|
| `qwen3.5-9b-deepseek-v4-flash-mtp` | 189/200 | 94 % (90–97 %) | 0.85 | 0 | 4 |
| `qwen3.5-4b-mtp` | 186/200 | 93 % (89–96 %) | 0.85 | 3 | 4 |
| `qwen3-8b` | 180/200 | 90 % (85–93 %) | 0.90 | 0 | 3 |
| `qwen2.5-coder-7b-instruct` | 36/200 | 18 % (13–24 %) | 0.15 | 14 | 0 |

- The intervals of the first three models overlap: this set does not rank them.
- The Wilson interval treats the 200 attempts as independent, so it shows only the variation between repeats on
  these 20 tasks. Attempts on the same task are strongly related; resampling the tasks gives about twice as wide
  intervals (85–100 % instead of 90–97 % for the first model).
- `qwen3-8b` never finished one of the four-step chains (0/10); every model mostly reported a transient tool error to
  the user instead of retrying it.
- `qwen2.5-coder-7b-instruct` failed 164 attempts, 149 of them because it wrote the tool call as plain text, so the
  set measures mainly this format problem for it, not its other abilities.
- One machine, one task set, local settings: the numbers describe this setup, not the models in general.

### Probes (advanced)

Run from `harness\`. They load models on the GPU and write a JSON result into `results\`.

| Command | What it checks |
|---|---|
| `node spec-probe.ts --plan ..\configs\spec-probe.local.json --steps P1,P2` | Speculative decoding: draft model and MTP loads, draft statistics, speed against speculation off. Copy `configs\spec-probe.example.json` first; `--dry-run` checks the plan without the GPU |
| `node tools-probe.ts --models qwen3-8b` | Tool calls through the SDK: what the model sends, the round trip of a tool result, an abort |

## Choosing models

`configs\quick.json` contains a sample model list. To use your own, copy it to `configs\quick.local.json` and edit the
`models` list; that file is picked up automatically and is not tracked by git. `lms ls` shows the model keys. Any
other grid file can be run with `--grid <file>`. Repeats, prompt length and timeouts are command line options, not part
of the grid (`.\bench run --help`). Agent runs take the model key directly (`--model`).

## Folders

| Folder | Contents |
|---|---|
| `configs\` | Sweep grids (model list, default load settings, the configurations to compare), sampling profiles for agent runs and the sample plan of the speculative decoding probe |
| `runner\` | Python code: the `bench` CLI, the sweep runner with its status and control files, the evaluation, the agent run (loading, starting the harness, checking the answers) and shared helpers |
| `harness\` | TypeScript code on the LM Studio SDK: the model loader used by both runs, the agent harness (`run-tasks.ts` and `agent\`: tool loop, tools, sandbox, trace) and the probes. Search, git and shell tools are planned here, behind a sandbox restriction |
| `tasks\` | Agent tasks with their checks, and the fixture files copied into each task's sandbox |
| `tests\` | Offline tests (no GPU) and one live control test that uses the GPU |
| `tools\` | PDF export of the documents and the diagram generator |
| `docs\` | [Roadmap](docs/roadmap.md), [requirements](docs/requirements.md), [architecture](docs/architecture.md), [findings](docs/findings.md), [failure taxonomy](docs/failure_taxonomy.md) and [load parameters](docs/lmstudio_load_parameters.md), in English and Hungarian |

Created while running, not tracked by git:

| Folder | Contents |
|---|---|
| `results\` | Raw results: one JSON line per sweep job or agent attempt, agent traces and sandboxes, probe results |
| `report\` | Sweep tables and evaluation reports in Markdown |
| `state\` | Sweep plans, live status and the control file behind pause, resume and stop |
| `inventory\` | Model list snapshots written by the smoke test |

## Tests

```
python -m unittest discover -s tests   # all offline Python tests at once
cd harness; npm.cmd test; npm.cmd run typecheck; cd ..   # offline (TypeScript tests and type check)
python tests\test_agent.py           # offline (also runs the harness with scripted model replies)
python tests\test_sweep_logic.py      # offline
python tests\test_evaluate.py         # offline
python tests\test_stream_errors.py    # offline
python tests\live_control_test.py     # uses the GPU (small model, a few minutes): pause / stop / resume
```

## License

[MIT](LICENSE)

---

*Built with AI assistance.*
