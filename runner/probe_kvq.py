#!/usr/bin/env python3
"""Probe: is the saved KV-cache quantization (q8_0, per-model default) applied on REST loads?

No config files are written. Method: load the 1B model twice via REST with parallel=1, flash attention on,
ctx 2048 and ctx 32768, measure VRAM growth between the two. KV growth per token for Llama-3.2-1B:
16 layers x 8 KV heads x 64 dim x 2 (K+V) = 16384 elements/token.
  fp16 : 2 bytes/elt      -> ~960 MiB extra for +30720 tokens
  q8_0 : 1.0625 bytes/elt -> ~510 MiB extra
The measured delta tells which one is in effect. Hard timeouts, no retries, always unloads.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402

MODEL = "llama-3.2-1b-instruct"
EL_PER_TOKEN = 16 * 8 * 64 * 2
res = {}
started = False
try:
    rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
    if "not running" in out.lower():
        smoke.sh([smoke.LMS, "server", "start"], 60)
        started = True
        time.sleep(3)
        rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
    smoke.BASE = f"http://127.0.0.1:{re.search(r'port\s+(\d+)', out).group(1)}"

    for ctx in (2048, 32768):
        smoke.sh([smoke.LMS, "unload", "--all"], 60)
        time.sleep(2)
        before = smoke.vram()[0]
        smoke.http_json("POST", "/api/v1/models/load",
                        {"model": MODEL, "context_length": ctx, "parallel": 1,
                         "flash_attention": True, "echo_load_config": True}, timeout=120)
        time.sleep(3)
        after = smoke.vram()[0]
        res[ctx] = {"before": before, "after": after, "delta": after - before}
        print(f"ctx={ctx}: VRAM {before} -> {after} MiB (delta {after - before})", flush=True)

    kv = res[32768]["delta"] - res[2048]["delta"]
    d_tok = 32768 - 2048
    fp16 = d_tok * EL_PER_TOKEN * 2 / 2**20
    q8 = d_tok * EL_PER_TOKEN * 1.0625 / 2**20
    print(f"KV growth measured: {kv} MiB | theory fp16 {fp16:.0f} MiB | theory q8_0 {q8:.0f} MiB")
    verdict = ("q8_0-like (saved default seems applied)" if abs(kv - q8) < abs(kv - fp16)
               else "fp16-like (saved default NOT applied, or not detectable)")
    print("verdict:", verdict)
    res["kv_growth_mib"], res["theory_fp16_mib"], res["theory_q8_mib"], res["verdict"] = kv, round(fp16), round(q8), verdict
except smoke.StepError as e:
    print(f"ABORTED ({e.kind}): {e}")
    res["abort"] = str(e)
finally:
    smoke.sh([smoke.LMS, "unload", "--all"], 60)
    if started:
        smoke.sh([smoke.LMS, "server", "stop"], 30)
    out = Path(__file__).resolve().parent.parent / "results" / f"probe_kvq_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("result file:", out)
