#!/usr/bin/env python3
"""Smoke test for the LM Studio benchmark harness.

Goal: prove the basic measurement chain works on one model before anything bigger is built:
  inventory dump -> preflight (GPU/server) -> load estimate -> load -> read back config ->
  streamed generation (TTFT, tok/s, peak VRAM) -> tool-call probe -> unload -> verify clean state.

Safety rules (by design):
  * Every external step has a hard timeout. Expensive steps (load, generation) are NEVER retried.
  * On timeout/failure the run stops, cleans up (unloads the model) and exits non-zero with a
    clear "ABORTED" message so the user is told instead of the script looping.
  * Only stdlib. Talks to LM Studio via `lms.exe` and the local server on 127.0.0.1.
"""
import argparse
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LMS = os.path.join(os.environ.get("USERPROFILE", ""), ".lmstudio", "bin", "lms.exe")
BASE = "http://127.0.0.1:1234"
IDENT = "bench-smoke"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class StepError(Exception):
    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind  # "timeout" | "fail"


def log(msg):
    print(msg, flush=True)


def sh(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise StepError("timeout", f"command timed out after {timeout}s: {' '.join(cmd[:3])} ...")
    except FileNotFoundError as e:
        raise StepError("fail", f"executable not found: {e}")
    out = ANSI.sub("", (p.stdout or "") + (p.stderr or ""))
    return p.returncode, out


def vram():
    rc, out = sh(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                  "--format=csv,noheader,nounits"], 15)
    if rc != 0:
        raise StepError("fail", "nvidia-smi failed: " + out.strip()[:200])
    used, total = [int(x) for x in out.strip().splitlines()[0].split(",")]
    return used, total


class VramSampler(threading.Thread):
    def __init__(self, period=0.5):
        super().__init__(daemon=True)
        self.period, self.peak, self._stop_evt = period, 0, threading.Event()

    def run(self):
        while not self._stop_evt.is_set():
            try:
                self.peak = max(self.peak, vram()[0])
            except Exception:
                pass
            self._stop_evt.wait(self.period)

    def stop(self):
        self._stop_evt.set()
        self.join(timeout=5)
        return self.peak


def http_json(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (TimeoutError, socket.timeout):
        raise StepError("timeout", f"HTTP {method} {path} timed out after {timeout}s")
    except urllib.error.HTTPError as e:
        raise StepError("fail", f"HTTP {e.code} on {path}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise StepError("timeout", f"HTTP {method} {path} timed out after {timeout}s")
        raise StepError("fail", f"HTTP {method} {path} failed: {e.reason}")


def stream_chat(model, messages, max_tokens, total_timeout, idle_timeout=45, on_chunk=None):
    body = json.dumps({"model": model, "messages": messages, "temperature": 0, "seed": 1,
                       "max_tokens": max_tokens, "stream": True,
                       "stream_options": {"include_usage": True}}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    t_first = t_last = None
    content, reasoning, usage, chunks = [], [], None, 0
    finished = False
    try:
        with urllib.request.urlopen(req, timeout=idle_timeout) as resp:
            for raw in resp:
                if on_chunk:
                    on_chunk()  # may raise to abort the generation (pause/stop --now)
                if time.perf_counter() - t0 > total_timeout:
                    raise StepError("timeout", f"generation exceeded {total_timeout}s total")
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    finished = True
                    break
                obj = json.loads(payload)
                if obj.get("usage"):
                    usage = obj["usage"]
                for ch in obj.get("choices", []):
                    finished = finished or bool(ch.get("finish_reason"))
                    d = ch.get("delta", {})
                    c = d.get("content") or ""
                    r = d.get("reasoning_content") or d.get("reasoning") or ""
                    if c or r:
                        now = time.perf_counter()
                        t_first = t_first or now
                        t_last = now
                        chunks += 1
                    content.append(c)
                    reasoning.append(r)
    except (TimeoutError, socket.timeout):
        raise StepError("timeout", f"no data for {idle_timeout}s (idle timeout)")
    except urllib.error.HTTPError as e:
        raise StepError("fail", f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise StepError("timeout", f"connect/idle timeout ({idle_timeout}s)")
        raise StepError("fail", f"request failed: {e.reason}")
    except (OSError, http.client.HTTPException, ValueError) as e:  # reset, truncated or garbled stream
        raise StepError("fail", f"connection broke during generation: {e!r}")
    if not finished:
        raise StepError("fail", "stream ended before the generation finished")
    m = {"ttft_s": round(t_first - t0, 3) if t_first else None,
         "total_s": round(time.perf_counter() - t0, 3),
         "stream_chunks": chunks, "usage": usage,
         "content": "".join(content), "reasoning_chars": len("".join(reasoning))}
    if t_first and t_last and t_last > t_first:
        n = (usage or {}).get("completion_tokens") or chunks
        m["decode_tok_s"] = round((n - 1) / (t_last - t_first), 2) if n > 1 else None
    return m


class Recorder:
    def __init__(self):
        self.steps = []

    def run(self, name, fn):
        t = time.perf_counter()
        log(f"[..] {name}")
        try:
            res = fn()
            self.steps.append({"name": name, "status": "ok", "seconds": round(time.perf_counter() - t, 2),
                               "detail": res})
            log(f"[ok] {name} ({time.perf_counter() - t:.1f}s)")
            return res
        except StepError as e:
            self.steps.append({"name": name, "status": e.kind, "seconds": round(time.perf_counter() - t, 2),
                               "detail": str(e)})
            log(f"[{e.kind.upper()}] {name}: {e}")
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-8b", help="LM Studio model key (see `lms ls`)")
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--load-timeout", type=int, default=240)
    ap.add_argument("--gen-timeout", type=int, default=180)
    ap.add_argument("--min-free-mib", type=int, default=3500)
    ap.add_argument("--max-util", type=int, default=30, help="abort if GPU utilization above this %%")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "inventory").mkdir(exist_ok=True)
    out_path = ROOT / "results" / f"smoke_{args.model}_{ts}.json"
    rec = Recorder()
    result = {"model": args.model, "ctx": args.ctx, "started": ts, "env": {}, "metrics": {},
              "outcome": "aborted"}
    loaded = False
    started_server = False
    exit_code = 3
    try:
        # --- inventory + environment (read only)
        def inventory():
            rc, out = sh([LMS, "ls", "--json"], 60)
            if rc != 0:
                raise StepError("fail", "lms ls failed: " + out[:200])
            data = json.loads(out[out.index("["):])
            (ROOT / "inventory" / f"lms_ls_{ts}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
            m = next((x for x in data if x.get("modelKey") == args.model), None)
            if not m:
                raise StepError("fail", f"model key not found: {args.model}")
            result["model_meta"] = {k: m.get(k) for k in
                                    ("modelKey", "path", "sizeBytes", "architecture", "quantization",
                                     "paramsString", "maxContextLength", "vision", "trainedForToolUse")}
            return {"models_total": len(data), "target": result["model_meta"]}
        rec.run("inventory (lms ls --json)", inventory)

        def env():
            used, total = vram()
            rc, drv = sh(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], 15)
            rc2, rt = sh([LMS, "runtime", "ls"], 30)
            result["env"] = {"gpu_driver": drv.strip(), "vram_used_baseline_mib": used, "vram_total_mib": total,
                             "runtime_ls": rt.strip()[:1500] if rc2 == 0 else f"unavailable (rc={rc2})",
                             "python": sys.version.split()[0]}
            rcu, u = sh(["nvidia-smi", "--query-gpu=utilization.gpu",
                         "--format=csv,noheader,nounits"], 15)
            util = int(u.strip().splitlines()[0]) if rcu == 0 and u.strip() else None
            result["env"]["gpu_util_baseline_pct"] = util
            if total - used < args.min_free_mib:
                raise StepError("fail", f"only {total - used} MiB VRAM free (< {args.min_free_mib}); "
                                        "close GPU-heavy apps (e.g. games) and rerun")
            if util is not None and util > args.max_util:
                raise StepError("fail", f"GPU already {util}% busy (> {args.max_util}%); "
                                        "speed numbers would be distorted. Close GPU-heavy apps and rerun")
            return result["env"]
        rec.run("preflight (GPU, runtime info)", env)

        # --- server
        def server():
            global BASE
            nonlocal started_server
            rc, out = sh([LMS, "server", "status"], 30)
            if "not running" in out.lower():
                rc, out = sh([LMS, "server", "start"], 60)
                if rc != 0:
                    raise StepError("fail", "lms server start failed: " + out[:200])
                started_server = True
                rc, out = sh([LMS, "server", "status"], 30)
            # LM Studio reuses the LAST port; never assume 1234
            mport = re.search(r"port\s+(\d+)", out)
            if not mport:
                raise StepError("fail", "cannot read server port from: " + out.strip()[:200])
            BASE = f"http://127.0.0.1:{mport.group(1)}"
            result["env"]["server_base"] = BASE
            deadline = time.time() + 40
            while time.time() < deadline:
                try:
                    http_json("GET", "/v1/models", timeout=5)
                    return {"started_by_script": started_server}
                except StepError:
                    time.sleep(1)
            raise StepError("timeout", "server did not answer /v1/models within 40s")
        rec.run("server up", server)

        # --- estimate (non-fatal)
        def estimate():
            rc, out = sh([LMS, "load", args.model, "--gpu", "max", "-c", str(args.ctx),
                          "--estimate-only", "-y"], 90)
            return {"rc": rc, "text": out.strip()[:800]}
        try:
            rec.run("load estimate (--estimate-only)", estimate)
        except StepError:
            log("    (estimate failed; continuing, non-fatal)")

        # --- load (no retry)
        def load():
            nonlocal loaded
            before, _ = vram()
            t = time.perf_counter()
            rc, out = sh([LMS, "load", args.model, "--gpu", "max", "-c", str(args.ctx),
                          "--identifier", IDENT, "-y"], args.load_timeout)
            if rc != 0:
                raise StepError("fail", "lms load failed: " + out.strip()[:400])
            loaded = True
            after, total = vram()
            result["metrics"]["load_s"] = round(time.perf_counter() - t, 2)
            result["metrics"]["vram_after_load_mib"] = after
            result["metrics"]["vram_delta_load_mib"] = after - before
            return {"vram_before": before, "vram_after": after, "out": out.strip()[-300:]}
        rec.run("load model (gpu=max, ctx=%d)" % args.ctx, load)

        # --- read back effective config (non-fatal)
        def readback():
            for path in (f"/api/v0/models/{IDENT}", "/api/v0/models"):
                try:
                    d = http_json("GET", path, timeout=10)
                    result["effective_config"] = d
                    return d
                except StepError:
                    continue
            raise StepError("fail", "could not read effective config from /api/v0/models")
        try:
            rec.run("read back loaded config", readback)
        except StepError:
            log("    (readback failed; continuing, non-fatal)")

        # --- generation
        def gen():
            sampler = VramSampler()
            sampler.start()
            try:
                m = stream_chat(IDENT, [{"role": "user", "content":
                                         "Count from 1 to 10, separated by commas. Output only the numbers."}],
                                max_tokens=1024, total_timeout=args.gen_timeout)
            finally:
                peak = sampler.stop()
            m["vram_peak_mib"] = peak
            ok = bool(re.search(r"\b1\D+2\D+3\D+4\D+5\D+6\D+7\D+8\D+9\D+10\b", m["content"]))
            m["answer_check_passed"] = ok
            result["metrics"].update({k: m.get(k) for k in
                                      ("ttft_s", "decode_tok_s", "total_s", "vram_peak_mib",
                                       "answer_check_passed", "usage")})
            return m
        rec.run("generate (streamed, temp=0, seed=1)", gen)

        # --- tool-call probe (functional, non-fatal on a negative result)
        def toolprobe():
            body = {"model": IDENT, "temperature": 0, "seed": 1, "max_tokens": 1024,
                    "messages": [{"role": "user", "content":
                                  "What time is it in Budapest? Use the get_time tool."}],
                    "tools": [{"type": "function", "function": {
                        "name": "get_time", "description": "Get the current time in a city",
                        "parameters": {"type": "object",
                                       "properties": {"city": {"type": "string"}},
                                       "required": ["city"]}}}]}
            t = time.perf_counter()
            d = http_json("POST", "/v1/chat/completions", body, timeout=args.gen_timeout)
            msg = d["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            res = {"seconds": round(time.perf_counter() - t, 2), "n_tool_calls": len(calls)}
            if calls:
                fn = calls[0].get("function", {})
                try:
                    a = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    a = {}
                res.update({"name": fn.get("name"), "arguments": a,
                            "passed": fn.get("name") == "get_time" and "budapest" in str(a.get("city", "")).lower()})
            else:
                res.update({"passed": False, "content_head": (msg.get("content") or "")[:200]})
            result["metrics"]["tool_call_probe_passed"] = res["passed"]
            return res
        rec.run("tool-call probe (mock get_time)", toolprobe)

        result["outcome"] = "completed"
        exit_code = 0
    except StepError as e:
        result["outcome"] = "aborted"
        result["abort_reason"] = f"{e.kind}: {e}"
        log(f"\nABORTED ({e.kind}): {e}")
        log("No retries were attempted. Cleaning up, then stopping; user input needed.")
    except Exception as e:  # unexpected
        result["outcome"] = "error"
        result["abort_reason"] = f"unexpected: {e!r}"
        log(f"\nERROR (unexpected): {e!r}")
    finally:
        # --- cleanup: always unload, verify state
        try:
            if loaded:
                rc, out = sh([LMS, "unload", IDENT], 60)
                log(f"[cleanup] unload rc={rc}")
            rc, ps = sh([LMS, "ps"], 30)
            used, _ = vram()
            result["cleanup"] = {"lms_ps": ps.strip()[:300], "vram_used_after_mib": used}
            if started_server:
                sh([LMS, "server", "stop"], 30)
                result["cleanup"]["server_stopped"] = True
        except Exception as e:
            result["cleanup"] = {"error": repr(e)}
            log(f"[cleanup] problem: {e!r}  -> check `lms ps` manually")
        result["steps"] = rec.steps
        out_path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        log(f"\nresult file: {out_path}")
        log("metrics: " + json.dumps(result["metrics"], ensure_ascii=False))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
