# lmstudio-tuner-bench

[Magyar](README.hu.md)

Benchmark local LLMs and tune their load parameters in LM Studio on your own hardware. Quality test suites and a web
dashboard are planned ([roadmap](docs/roadmap.md)).

> Unofficial tool, not affiliated with the makers of LM Studio.
> Early stage: tried on a single machine only.

## Motivation

I downloaded a lot of models and then wanted to know, on my own machine, what each of them can do, what I can use it
for well, and how to run it in an optimized way. Finding that out by hand caused plenty of headaches. LM Studio can
choose load settings automatically, but I found no built-in way to measure and compare many models and settings
systematically on my own tasks, so I started building it.

## Requirements

- Windows, NVIDIA GPU (`nvidia-smi`)
- LM Studio with the `lms` CLI (tested with 1.2.0)
- Python (tested with 3.15.2), no external packages
- Node.js 24 or newer (tested with 26.13.0) and the LM Studio SDK: run `npm.cmd install --ignore-scripts` in `harness\`
- Microsoft Edge, only for the PDF export of the documents

**Known limitation:** models are loaded through the official LM Studio SDK, and the SDK's API port is read from an
internal LM Studio file (`~\.lmstudio\apps\bionic\.internal\http-server.json`), which may differ on other
installations (override with the `LMS_API_FILE` environment variable). The application has to be running. Details:
[load parameters](docs/lmstudio_load_parameters.md).

## Usage

In PowerShell, from the project folder. Run the sweep in one terminal (live log) and control it from another.

| Command | What it does |
|---|---|
| `.\bench run --dry-run` | Lists the jobs without starting anything |
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

## Behaviour

- On pause and stop the model is unloaded, and a server started by the tool is stopped.
- `--now` takes effect at the next checkpoint. A model load in progress is not interrupted but awaited (240 s at most).
- If the GPU is busy or someone else loaded a model, the run pauses by itself, checks again every 90 s and continues
  once the machine is free (`--busy-retry <seconds>`, `0` waits for `resume`). A pause requested with `bench pause`
  never ends by itself.
- Failed steps are never retried automatically. Two consecutive timeouts abort the run.
- If the runtime or driver version changes, the run does not continue without `--allow-env-change`.
- LM Studio's per-model settings files are not modified. The runner loads its model as `bench-sweep`; if a killed run
  left it loaded, the next start unloads it.

## Choosing models

`configs\quick.json` contains a sample model list. To use your own, copy it to `configs\quick.local.json` and edit the
`models` list; that file is picked up automatically and is not tracked by git. `lms ls` shows the model keys. Any
other grid file can be run with `--grid <file>`. Repeats, prompt length and timeouts are command line options, not part
of the grid (`.\bench run --help`).

## Folders

`configs\` grids · `runner\` scripts · `results\` raw results · `report\` tables · `state\` run state ·
`harness\` SDK loader and probes · `docs\` documentation · `tools\` utilities · `tests\` tests

## Tests

```
node --test harness\load-config.test.ts   # offline
python tests\test_sweep_logic.py      # offline
python tests\test_evaluate.py         # offline
python tests\test_stream_errors.py    # offline
python tests\live_control_test.py     # uses the GPU (small model, a few minutes): pause / stop / resume
```

## License

[MIT](LICENSE)

---

*Built with AI assistance.*
