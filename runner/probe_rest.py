#!/usr/bin/env python3
"""Probe: which load parameters does the LM Studio REST API accept, and which are really applied?

Method: use a tiny model (fast load), send load requests with `echo_load_config`, record the raw
response. Unknown fields are either rejected (HTTP 4xx, costs nothing) or accepted; the echoed config
is the ground truth for what was applied. Every request has a hard timeout; nothing is retried.
Always unloads and restores the server state (stops the server only if this script started it).
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402  (reuse helpers: sh, http_json, StepError, LMS)

ROOT = Path(__file__).resolve().parent.parent
MODEL = "llama-3.2-1b-instruct"  # 1.3 GB, loads in seconds
BASE_REQ = {"model": MODEL, "context_length": 2048, "echo_load_config": True}

ATTEMPTS = [
    ("A: minimal + echo", {}),
    ("B: flash/batch/kv-offload", {"flash_attention": False, "eval_batch_size": 256,
                                   "offload_kv_cache_to_gpu": True}),
    ("C: bogus field (does API reject unknown fields?)", {"bogus_field_xyz": 1}),
    ("D: kv quant (snake_case guess)", {"k_cache_quantization_type": "q8_0",
                                        "v_cache_quantization_type": "q8_0"}),
    ("E: threads/parallel guesses", {"cpu_thread_pool_size": 4, "parallel": 1}),
    ("F: batch guesses", {"physical_batch_size": 256, "n_batch": 256}),
]


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = {"started": ts, "model": MODEL, "attempts": []}
    started = False
    try:
        rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
        if "not running" in out.lower():
            rc, out = smoke.sh([smoke.LMS, "server", "start"], 60)
            started = True
            rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
        port = re.search(r"port\s+(\d+)", out).group(1)
        smoke.BASE = f"http://127.0.0.1:{port}"
        time.sleep(2)
        log["server"] = smoke.BASE

        # endpoint discovery (read only)
        for path in ("/api/v1/models", "/api/v0/models"):
            try:
                d = smoke.http_json("GET", path, timeout=15)
                log.setdefault("discovery", {})[path] = "ok (%s)" % (
                    f"{len(d.get('data', d.get('models', [])))} items" if isinstance(d, dict) else type(d).__name__)
            except smoke.StepError as e:
                log.setdefault("discovery", {})[path] = f"{e.kind}: {e}"

        for name, extra in ATTEMPTS:
            body = dict(BASE_REQ)
            body.update(extra)
            t = time.perf_counter()
            entry = {"attempt": name, "request": body}
            try:
                d = smoke.http_json("POST", "/api/v1/models/load", body, timeout=120)
                entry.update({"status": "accepted", "response": d})
            except smoke.StepError as e:
                entry.update({"status": e.kind, "error": str(e)})
            entry["seconds"] = round(time.perf_counter() - t, 2)
            print(f"[{entry['status']}] {name} ({entry['seconds']}s)", flush=True)
            log["attempts"].append(entry)
            if entry["status"] == "accepted":
                rc, o = smoke.sh([smoke.LMS, "unload", "--all"], 60)
                entry["unload_rc"] = rc
            if entry["status"] == "timeout":
                print("Timeout -> stopping probe; no retries.", flush=True)
                break
    finally:
        try:
            smoke.sh([smoke.LMS, "unload", "--all"], 60)
            rc, ps = smoke.sh([smoke.LMS, "ps"], 30)
            log["final_ps"] = ps.strip()[:200]
            if started:
                smoke.sh([smoke.LMS, "server", "stop"], 30)
                log["server_stopped"] = True
        except Exception as e:
            log["cleanup_error"] = repr(e)
        p = ROOT / "results" / f"probe_rest_{ts}.json"
        p.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
        print("result file:", p, flush=True)


if __name__ == "__main__":
    main()
