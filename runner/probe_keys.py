#!/usr/bin/env python3
"""Probe: find the real REST parameter names for KV-cache quantization, CPU threads, GPU offload, etc.

Trick: the load endpoint validates strictly. A guessed key that does not exist is rejected with
'Unrecognized key(s)'. A key that exists but gets a wrong-typed value (an object) is rejected with a
type error instead. Both outcomes are rejected requests -> nothing is loaded, nothing is changed.
For recognized keys a second request with a bogus string value reveals the allowed enum values.
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODEL = "llama-3.2-1b-instruct"

CANDIDATES = [
    # KV cache quantization
    "kv_cache_quantization_type", "cache_type_k", "cache_type_v", "k_cache_type", "v_cache_type",
    "kv_cache_type", "k_cache_quantization", "v_cache_quantization", "kv_cache_quantization",
    "k_cache_quant", "v_cache_quant", "k_cache_quant_type", "v_cache_quant_type",
    "key_cache_type", "value_cache_type", "quantize_kv_cache", "cache_type", "kv_quantization",
    "llama_k_cache_quantization_type", "llama_v_cache_quantization_type",
    # CPU threads
    "cpu_threads", "n_threads", "threads", "thread_pool_size", "cpu_thread_count", "num_threads",
    "cpu_thread_pool", "cpu_threads_count",
    # GPU offload
    "gpu_offload", "gpu_offload_ratio", "gpu", "n_gpu_layers", "gpu_layers", "num_gpu_layers",
    "offload_ratio", "gpu_ratio", "gpu_offload_layers",
    # misc
    "keep_model_in_memory", "try_mmap", "mmap", "use_mmap", "unified_kv_cache", "num_experts",
    "force_model_cpu_experts", "on_demand_tensor_loading", "seed", "identifier", "ttl",
    "rope_frequency_base", "rope_frequency_scale", "llama_cpp_args", "extra_args", "engine_args",
]


def classify(msg, key):
    m = re.search(r"Unrecognized key\(s\) in object: (.*?)(?:\"|$)", msg)
    if m and f"'{key}'" in m.group(1):
        return "unknown"
    if "Unrecognized key" in msg:
        return "unknown?"  # another key was unrecognized; ours unclear
    return "RECOGNIZED"


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = {"started": ts, "results": {}, "docs": {}}
    started = False
    try:
        rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
        if "not running" in out.lower():
            smoke.sh([smoke.LMS, "server", "start"], 60)
            started = True
            rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
        smoke.BASE = f"http://127.0.0.1:{re.search(r'port\s+(\d+)', out).group(1)}"
        time.sleep(2)

        for path in ("/openapi.json", "/api/v1/openapi.json", "/docs"):
            try:
                d = smoke.http_json("GET", path, timeout=10)
                log["docs"][path] = "ok: " + json.dumps(d)[:300]
            except smoke.StepError as e:
                log["docs"][path] = f"{e.kind}"

        recognized = []
        for key in CANDIDATES:
            body = {"model": MODEL, key: {"x": 1}}
            try:
                d = smoke.http_json("POST", "/api/v1/models/load", body, timeout=30)
                log["results"][key] = {"class": "ACCEPTED-LOADED?!", "resp": str(d)[:200]}
                smoke.sh([smoke.LMS, "unload", "--all"], 60)
                recognized.append(key)
                continue
            except smoke.StepError as e:
                msg = str(e)
            c = classify(msg, key)
            log["results"][key] = {"class": c, "msg": msg[:350] if c != "unknown" else ""}
            if c in ("RECOGNIZED", "unknown?"):
                recognized.append(key)
            print(f"{c:11s} {key}", flush=True)

        # enum discovery for recognized keys
        for key in recognized:
            try:
                smoke.http_json("POST", "/api/v1/models/load", {"model": MODEL, key: "zzz_bogus"}, timeout=30)
                log["results"][key]["enum_probe"] = "accepted a bogus string (!)"
                smoke.sh([smoke.LMS, "unload", "--all"], 60)
            except smoke.StepError as e:
                log["results"][key]["enum_probe"] = str(e)[:500]
    finally:
        try:
            smoke.sh([smoke.LMS, "unload", "--all"], 60)
            rc, ps = smoke.sh([smoke.LMS, "ps"], 30)
            log["final_ps"] = ps.strip()[:120]
            if started:
                smoke.sh([smoke.LMS, "server", "stop"], 30)
                log["server_stopped"] = True
        except Exception as e:
            log["cleanup_error"] = repr(e)
        p = ROOT / "results" / f"probe_keys_{ts}.json"
        p.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
        print("result file:", p, flush=True)


if __name__ == "__main__":
    main()
