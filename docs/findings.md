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
