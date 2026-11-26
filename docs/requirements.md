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

### Open

- Interface between the Python core and the TypeScript harness (process boundary, trace format).
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
