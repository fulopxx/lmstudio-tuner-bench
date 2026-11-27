# Measurement findings

[Magyar](findings.hu.md)

General results of measurements. Load settings and how they were verified: [load parameters](lmstudio_load_parameters.md).
Open points: [roadmap](roadmap.md), section 4.

## Clean sweeps, 2026-11-26

These supersede the 56-job trial run of the same day, which ran on a busy machine.

One machine (RTX 2070, 8 GB), 132 jobs on 7B to 14B models, all successful, 3 repeats each, prompts of about 1800 and
6000 tokens. Neither prompt filled a 16k context, and output quality was not measured.

- Where full GPU offload fitted without spilling into shared memory, every partial offload was slower (tested on 12–14B
  models only). Where VRAM overflowed, a partial offload was often faster.
- Where the model fits, `f16` KV decoded as fast as `q8_0` or up to about 9 % faster.
- Eval batch 512 against 2048 made little difference when the model fits; near the VRAM limit it sometimes doubled the
  decode speed.
- Near the VRAM limit, speed depends on the VRAM used by other programs: one configuration decoded at 34 t/s in one run
  and at 6 t/s in another (the prompt length differed too).
- With the longer prompt, decode was 4 to 22 % slower for models that fit; the cause (probably prompt length) is not
  verified.

## Speculative decoding trial (phase 0), 2026-11-26

Same machine, 4k context, single trial runs with the LM Studio default of 3 draft tokens; details in the
[requirements](requirements.md), section 5.

- A separate draft model (1.5B Q8_0 for a 7B Q4 coder model) made decoding slower (−12 % on code, −44 % on the synthetic
  prompt) although 76 % of the draft tokens were accepted on code. Probable reason (not verified): on this GPU decoding is
  limited by memory bandwidth, and a draft model at about 40 % of the main model's size costs more than it saves.
- Built-in MTP heads were faster on three models (+4 % to +33 %), with no extra VRAM.
- Speculation is switched at load only; the REST chat endpoint returns the draft counters.

## Agent tasks, first live run of the M1 set, 2026-11-27

Same machine, 20 tasks, five attempts each, sampling per model card; details in the
[requirements](requirements.md), section 3, and the [failure taxonomy](failure_taxonomy.md).

- Three models that call tools passed 90 to 96 % of the attempts; their intervals overlap at five repeats.
- 74 of the 83 failures of a 7B coder model were tool calls written as text; for such a model the task set measures
  only the format problem.
- A transient tool error was retried by almost no model: they reported the error to the user instead.
- The manual review of the failures found four gaps in the keyword-based rules; a categorizer of this kind needs
  such a review after every new task set.
