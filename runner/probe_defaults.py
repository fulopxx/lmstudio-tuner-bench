#!/usr/bin/env python3
"""Probe: do per-model default-config values (threads, KV quant) flow into a REST load?
Loads the tiny Llama-3.2-1B once with echo_load_config, prints the applied config, unloads, restores server."""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402

started = False
try:
    rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
    if "not running" in out.lower():
        smoke.sh([smoke.LMS, "server", "start"], 60)
        started = True
        time.sleep(3)
        rc, out = smoke.sh([smoke.LMS, "server", "status"], 30)
    smoke.BASE = f"http://127.0.0.1:{re.search(r'port\s+(\d+)', out).group(1)}"
    d = smoke.http_json("POST", "/api/v1/models/load",
                        {"model": "llama-3.2-1b-instruct", "context_length": 2048,
                         "echo_load_config": True}, timeout=120)
    cfg = d.get("load_config", {})
    cfg.pop("prompt_template", None)
    print(json.dumps(cfg, indent=1))
except smoke.StepError as e:
    print(f"ERROR ({e.kind}): {e}")
finally:
    smoke.sh([smoke.LMS, "unload", "--all"], 60)
    if started:
        smoke.sh([smoke.LMS, "server", "stop"], 30)
    print(smoke.sh([smoke.LMS, "ps"], 30)[1].strip()[:60])
