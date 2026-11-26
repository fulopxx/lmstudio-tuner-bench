#!/usr/bin/env python3
"""Speed/memory sweep over (model x load configuration) with live status, pause, stop and resume.

  bench run --grid configs/quick.json [--models a,b] [--dry-run]
  bench status [--watch] [--jobs]
  bench pause [--now]      wait; GPU is freed (model unloaded, LM Studio files restored)
  bench resume             continue (same process if it is paused, otherwise restart from disk)
  bench resume --from 12   redo job 12 and everything after it
  bench resume --redo-failed
  bench stop [--now]       exit; can be resumed later, also after a reboot

Without --now, pause/stop take effect after the current job. With --now the current job is dropped
(it will be measured again) at the next checkpoint; a running model load is first allowed to return.

Rules: failed steps are never retried automatically; two consecutive timeouts abort the run; a busy
GPU or a model loaded by someone else pauses the run, which checks again every 90 s and continues by
itself once the machine is free (--busy-retry; a manual pause stays); only the runner's own model
instance is unloaded. Models are loaded through the LM Studio SDK (harness/load-model.ts), so LM Studio's
per-model config files are not touched; generation and measurement use the HTTP server.
"""
import argparse
import ctypes
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate  # noqa: E402
import smoke  # noqa: E402
from smoke import LMS, StepError, sh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
IDENTIFIER = "bench-sweep"  # the only model instance this runner loads and removes
STATE = ROOT / "state"
CONTROL = STATE / "control.json"
STATUS = STATE / "status.json"
LATEST = STATE / "latest.txt"
ACTIVE = ("starting", "running", "paused")
BUSY_RETRY_S = 90  # re-check interval while paused because the machine was not ready
HEARTBEAT_LATE_S = 20  # an older heartbeat is reported, and trusted only if the process still exists


def log(m):
    print(f"{datetime.now():%H:%M:%S} {m}", flush=True)


# ---------------------------------------------------------------- files, control channel
def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    for attempt in range(30):  # Windows: replace fails while a reader has the file open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(0.1)


def read_json(path, default=None):
    for _ in range(10):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.1)
    return default


def send(cmd, now=False):
    write_json(CONTROL, {"cmd": cmd, "now": now, "ts": time.time()})


def control():
    return read_json(CONTROL, {"cmd": "run", "now": False})


def process_created(pid):
    """Creation time of a running process as an integer; None if there is no such process. Together with
    the PID it identifies one process, even if Windows reuses the PID later (for example after a reboot)."""
    if os.name != "nt" or not pid:
        return None
    k = ctypes.WinDLL("kernel32")
    k.OpenProcess.argtypes, k.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        k.CloseHandle(handle)


def runner_alive(st):
    """An active run counts as alive while its heartbeat is fresh, or while the very process that wrote it
    still exists: a late heartbeat alone must not end the status view or allow a second runner."""
    if not st or st.get("state") not in ACTIVE:
        return False
    if time.time() - st.get("heartbeat", 0) < HEARTBEAT_LATE_S:
        return True
    created = st.get("pid_created")
    return created is not None and process_created(st.get("pid")) == created


# ---------------------------------------------------------------- plan and results
def build_jobs(grid, keys, meta):
    jobs = []
    for key in keys:
        for cfg in grid["configs"]:
            only = cfg.get("only_params")
            if only and meta[key].get("paramsString") not in only:
                continue
            s = dict(grid["defaults"])
            s.update({k: v for k, v in cfg.items() if k not in ("id", "only_params")})
            jobs.append({"n": len(jobs) + 1, "id": f"{key}|{cfg['id']}", "model": key,
                         "config": cfg["id"], "settings": s})
    return jobs


def latest_results(path):
    """job id -> last recorded row"""
    res = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                res[r["job_id"]] = r
    return res


def todo_jobs(jobs, results, redo_failed=False):
    out = []
    for j in jobs:
        r = results.get(j["id"])
        if r is None or r["status"] == "invalidated" or (redo_failed and r["status"] != "ok"):
            out.append(j)
    return out


def append_row(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(jobs, results, path, header):
    cols = ["model", "config", "status", "load_s", "vram_delta_mib", "vram_peak_mib",
            "prompt_tok_s", "decode_tok_s", "ttft_s", "near_vram_limit"]
    out = [f"# Sweep {header}", "", "| # | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for j in jobs:
        r = results.get(j["id"])
        if r and r["status"] != "invalidated":
            out.append(f"| {j['n']} | " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- GPU / environment
def gpu_state():
    rc, o = sh(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits"], 15)
    if rc != 0:
        raise StepError("fail", "nvidia-smi failed")
    return [int(x) for x in o.strip().splitlines()[0].split(",")]


def environment():
    rc, rt = sh([LMS, "runtime", "ls"], 30)
    runtime = next((ln.split()[0] for ln in rt.splitlines() if "✓" in ln and "llama.cpp" in ln), "?")
    rc, drv = sh(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 15)
    sdk = HARNESS / "node_modules" / "@lmstudio" / "sdk" / "package.json"
    loader = f"@lmstudio/sdk {json.loads(sdk.read_text(encoding='utf-8'))['version']}" if sdk.is_file() else None
    return {"runtime": runtime, "driver": drv.strip(), "loader": loader}


def sdk_load(model_path, settings, timeout):
    """Load through the Node helper (harness/load-model.ts). The model stays loaded after it exits."""
    request = {"model": model_path, "identifier": IDENTIFIER, "settings": settings, "timeoutMs": timeout * 1000}
    try:
        p = subprocess.run([shutil.which("node") or "node", "load-model.ts"], cwd=HARNESS, input=json.dumps(request),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        raise StepError("timeout", f"model load did not finish within {timeout + 30}s")
    line = next((ln for ln in reversed(p.stdout.splitlines()) if ln.startswith("RESULT:")), None)
    if p.returncode != 0 or not line:
        message = (p.stderr or p.stdout).strip()[-600:]
        kind = "timeout" if re.search(r"(?i)abort|timeout|timed out", message) else "fail"
        raise StepError(kind, "model load failed: " + message)
    return json.loads(line[len("RESULT:"):])


def model_catalog():
    rc, out = sh([LMS, "ls", "--json"], 60)
    if rc != 0:
        raise StepError("fail", "lms ls failed: " + out[:200])
    return {m["modelKey"]: m for m in json.loads(out[out.index("["):])}


class Interrupted(Exception):
    def __init__(self, cmd):
        super().__init__(cmd)
        self.cmd = cmd  # "pause" | "stop"


class Blocked(Exception):
    """The machine is not ready (GPU busy, foreign model loaded): pause and tell the user."""


class Fatal(Exception):
    pass


class Status:
    def __init__(self, base):
        self.data = dict(base, heartbeat=time.time(), pid=os.getpid(), pid_created=process_created(os.getpid()))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.update()
        self._thread = threading.Thread(target=self._beat, daemon=True)
        self._thread.start()

    def update(self, **kw):
        with self._lock:
            self.data.update(kw, heartbeat=time.time())
            try:
                write_json(STATUS, self.data)
            except OSError:
                pass  # status display must never kill a run

    def _beat(self):
        while not self._stop.wait(2):
            self.update()

    def close(self, **kw):
        self._stop.set()
        self._thread.join(timeout=5)
        self.update(**kw)


# ---------------------------------------------------------------- runner
class Runner:
    def __init__(self, run_id, plan, status):
        self.run_id, self.plan, self.status = run_id, plan, status
        self.o = plan["options"]
        self.started_server = False
        self.instance = None
        self._last_check = 0.0

    def checkpoint(self, in_job=True):
        c = control()
        if c["cmd"] in ("pause", "stop") and (c.get("now") or not in_job):
            raise Interrupted(c["cmd"])

    def on_chunk(self):
        if time.time() - self._last_check > 0.5:
            self._last_check = time.time()
            self.checkpoint()

    def phase(self, text):
        self.status.update(phase=text, phase_since=time.time())

    def ensure_ready(self):
        rc, ps = sh([LMS, "ps"], 30)
        if IDENTIFIER in ps:  # left over from a killed run: it is ours, so it may be removed
            log(f"unloading '{IDENTIFIER}' left over from an earlier run")
            sh([LMS, "unload", IDENTIFIER], 60)
            time.sleep(2)
            rc, ps = sh([LMS, "ps"], 30)
        if "No models are currently loaded" not in ps:
            raise Blocked("a model is loaded that this run did not load; unload it in LM Studio")
        samples = []
        for _ in range(3):
            samples.append(gpu_state())
            time.sleep(0.7)
        used, total = samples[-1][0], samples[-1][1]
        util = statistics.median(s[2] for s in samples)
        if total - used < self.o["min_free_mib"]:
            raise Blocked(f"only {total - used} MiB VRAM free (< {self.o['min_free_mib']}): game or GPU app running?")
        if util > self.o["max_util"]:
            raise Blocked(f"GPU {util}% busy (> {self.o['max_util']}%): close GPU-heavy apps")
        return used, total

    def ensure_server(self):
        rc, st = sh([LMS, "server", "status"], 30)
        if "not running" in st.lower():
            sh([LMS, "server", "start"], 60)
            self.started_server = True
            time.sleep(3)
            rc, st = sh([LMS, "server", "status"], 30)
        port = re.search(r"port\s+(\d+)", st)
        if not port:
            raise StepError("fail", "server port not found: " + st.strip()[:150])
        smoke.BASE = f"http://127.0.0.1:{port.group(1)}"

    def unload_ours(self):
        if self.instance:
            sh([LMS, "unload", self.instance], 60)
            self.instance = None
            time.sleep(2)

    def release(self):
        """Give the machine back: unload our model, stop our server."""
        for step in (self.unload_ours, self._stop_server):
            try:
                step()
            except Exception as e:
                log(f"[cleanup] {step.__name__}: {e!r}")

    def _stop_server(self):
        if self.started_server:
            sh([LMS, "server", "stop"], 30)
            self.started_server = False

    def measure(self, inst, tag):
        sampler = smoke.VramSampler()
        sampler.start()
        try:
            body = "\n".join(
                f"{i}. The sensor node {i} reports temperature {20 + i % 17} C, voltage "
                f"{3.0 + (i % 5) / 10:.1f} V and status code {i * 7 % 101}." for i in range(self.o["prompt_lines"]))
            prompt = f"Run id {tag}-{time.time_ns()}.\n{body}\n\nSummarize the data above in a short paragraph."
            m = smoke.stream_chat(inst, [{"role": "user", "content": prompt}],
                                  max_tokens=self.o["gen_tokens"], total_timeout=self.o["gen_timeout"],
                                  idle_timeout=self.o["gen_timeout"], on_chunk=self.on_chunk)
        finally:
            peak = sampler.stop()
        pt = (m.get("usage") or {}).get("prompt_tokens")
        return {"ttft_s": m["ttft_s"], "decode_tok_s": m.get("decode_tok_s"), "prompt_tokens": pt,
                "prompt_tok_s": round(pt / m["ttft_s"], 1) if pt and m["ttft_s"] else None,
                "vram_peak_mib": peak}

    def run_job(self, job, info):
        s = job["settings"]
        row = {"job_id": job["id"], "run": self.run_id, "model": job["model"], "config": job["config"],
               "settings": s, "model_path": info["path"], **self.plan["env"]}
        t_job = time.time()
        self.phase("checking GPU")
        _, total = self.ensure_ready()
        before = gpu_state()[0]
        self.ensure_server()
        self.checkpoint()
        self.phase("loading model")
        try:
            self.instance = IDENTIFIER  # so a half-finished load is cleaned up too
            loaded = sdk_load(info["path"], s, self.o["load_timeout"])
            row["load_s"] = round(loaded["loadSeconds"], 2)
            row["applied"], row["loaded_path"] = loaded["applied"], loaded["path"]
            if loaded["path"] != info["path"]:
                raise StepError("fail", f"wrong file loaded? got {loaded['path']}, expected {info['path']}")
            if loaded["mismatches"]:
                raise StepError("fail", "settings not applied: " + "; ".join(loaded["mismatches"]))
            self.checkpoint()
            time.sleep(2)
            row.update({"vram_before_mib": before, "vram_delta_mib": gpu_state()[0] - before})
            self.phase("warm-up generation")
            self.measure(self.instance, "warmup")
            runs = []
            for i in range(self.o["repeats"]):
                self.checkpoint()
                self.phase(f"measuring {i + 1}/{self.o['repeats']}")
                runs.append(self.measure(self.instance, f"run{i}"))
            row["runs"] = runs
            for k in ("ttft_s", "decode_tok_s", "prompt_tok_s", "vram_peak_mib"):
                vals = [r[k] for r in runs if r.get(k) is not None]
                row[k] = round(statistics.median(vals), 2) if vals else None
            row["near_vram_limit"] = bool(row["vram_peak_mib"] and row["vram_peak_mib"] > total - 250)
            row["status"] = "ok"
        except StepError as e:
            row.update({"status": e.kind, "error": str(e)})
        finally:
            self.unload_ours()
        row["job_s"] = round(time.time() - t_job, 1)
        row["finished"] = datetime.now().isoformat(timespec="seconds")
        return row

    def wait_paused(self, reason, auto=False):
        """Wait for `resume` or `stop`. With auto=True (the machine was not ready) the checks are also
        repeated every busy_retry_s seconds, until the user sends `pause` to keep the run paused."""
        self.release()
        retry = self.o.get("busy_retry_s", BUSY_RETRY_S) if auto else 0
        seen = control().get("ts")
        next_check = time.time() + retry

        def note(text):
            return f"{text} (checking again every {retry} s)" if retry else text

        self.status.update(state="paused", phase="paused", reason=note(reason))
        log(f"PAUSED: {note(reason)}\n         `bench resume` to continue, `bench stop` to exit.")
        while True:
            c = control()
            if c["cmd"] == "stop":
                return "stop"
            if c["cmd"] == "pause" and c.get("ts") != seen:  # explicit `bench pause`: stay paused
                retry, seen = 0, c.get("ts")
                self.status.update(reason="paused by user")
                log("automatic checks off; waiting for `bench resume`")
            if c["cmd"] == "run" or (retry and time.time() >= next_check):
                try:
                    if environment() != self.plan["env"] and not self.o.get("allow_env_change"):
                        raise Blocked("runtime or driver changed during the pause; `bench stop`, "
                                      "then `bench resume --allow-env-change`")
                    self.ensure_ready()
                    if control().get("ts") != c.get("ts"):
                        continue  # a new command arrived during the checks
                    send("run")
                    self.status.update(state="running", reason="")
                    log("RESUMED" if c["cmd"] == "run" else "RESUMED automatically")
                    return "run"
                except (Blocked, StepError) as e:
                    if c["cmd"] == "run" and control().get("ts") == c.get("ts"):
                        send("pause")
                        seen = control().get("ts")
                    next_check = time.time() + retry
                    self.status.update(reason=note(str(e)))
                    log(f"cannot resume yet: {e}")
            time.sleep(1)


def execute(run_id, redo_failed=False):
    run_dir = STATE / "runs" / run_id
    plan = read_json(run_dir / "plan.json")
    if not plan:
        log(f"no plan for run {run_id}")
        return 2
    results_path = ROOT / "results" / f"sweep_{run_id}.jsonl"
    report_path = ROOT / "report" / f"sweep_{run_id}.md"
    jobs = plan["jobs"]
    send("run")
    status = Status({"run": run_id, "state": "starting", "phase": "starting", "reason": "",
                     "total": len(jobs), "started": time.time()})
    runner = Runner(run_id, plan, status)
    final, reason, code, consecutive_timeouts = "aborted", "", 3, 0
    try:
        env = environment()
        if not shutil.which("node") or not env["loader"]:
            raise Fatal("Node.js or the SDK is missing: run `npm install --ignore-scripts` in harness/")
        if env != plan["env"]:
            if not plan["options"].get("allow_env_change"):
                raise Fatal(f"runtime/driver changed: plan {plan['env']} vs now {env}; "
                            "use --allow-env-change to continue anyway")
            plan["env"] = env
            write_json(run_dir / "plan.json", plan)
        meta = model_catalog()
        todo = todo_jobs(jobs, latest_results(results_path), redo_failed)
        log(f"run {run_id}: {len(todo)} of {len(jobs)} jobs to do")
        status.update(state="running")
        for job in todo:
            while True:
                try:
                    runner.checkpoint(in_job=False)
                    status.update(current={"n": job["n"], "model": job["model"], "config": job["config"]},
                                  job_started=time.time())
                    log(f"[{job['n']}/{len(jobs)}] {job['model']} / {job['config']}")
                    row = runner.run_job(job, meta[job["model"]])
                    break
                except Interrupted as e:
                    log(f"{e.cmd} requested; job {job['n']} will be measured again")
                    if e.cmd == "stop" or runner.wait_paused("paused by user") == "stop":
                        raise Interrupted("stop")
                except (Blocked, StepError) as e:  # StepError here = machine/server not usable
                    if isinstance(e, StepError):
                        row = {"job_id": job["id"], "run": run_id, "model": job["model"],
                               "config": job["config"], "status": e.kind, "error": str(e)}
                        runner.unload_ours()
                        break
                    send("pause")
                    if runner.wait_paused(str(e), auto=True) == "stop":
                        raise Interrupted("stop")
            append_row(results_path, row)
            write_report(jobs, latest_results(results_path), report_path, run_id)
            if row["status"] == "ok":
                log(f"      ok: vram +{row['vram_delta_mib']} MiB | prompt {row['prompt_tok_s']} t/s | "
                    f"decode {row['decode_tok_s']} t/s | {row['job_s']} s")
            else:
                log(f"      {row['status'].upper()}: {row.get('error')}")
            consecutive_timeouts = consecutive_timeouts + 1 if row["status"] == "timeout" else 0
            if consecutive_timeouts >= 2:
                raise Fatal("two consecutive timeouts; no further jobs started, user input needed")
        final, code = "done", 0
    except (Interrupted, KeyboardInterrupt):
        final, reason, code = "stopped", "stopped by user; `bench resume` continues", 0
    except Exception as e:
        reason = str(e) or repr(e)
        log(f"ABORTED: {reason}")
    finally:
        try:
            runner.release()
        finally:
            status.close(state=final, phase=final, reason=reason)
    log(f"{final.upper()}. report: {report_path}")
    return code


# ---------------------------------------------------------------- commands
def fmt_dur(s):
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def status_text(show_jobs=False):
    st = read_json(STATUS)
    run_id = (st or {}).get("run") or (LATEST.read_text().strip() if LATEST.exists() else None)
    if not run_id:
        return "no run yet", True
    plan = read_json(STATE / "runs" / run_id / "plan.json", {"jobs": []})
    results = latest_results(ROOT / "results" / f"sweep_{run_id}.jsonl")
    jobs = plan["jobs"]
    rows = [results[j["id"]] for j in jobs if j["id"] in results and results[j["id"]]["status"] != "invalidated"]
    ok = [r for r in rows if r["status"] == "ok"]
    state = (st or {}).get("state", "?")
    alive = runner_alive(st)
    if state in ACTIVE and not alive:
        state = "NOT RUNNING (process gone) -> `bench resume`"
    bar_n = int(30 * len(rows) / len(jobs)) if jobs else 0
    out = [f"run {run_id}   state: {state.upper() if alive else state}",
           f"[{'#' * bar_n}{'.' * (30 - bar_n)}] {len(rows)}/{len(jobs)} jobs   failed: {len(rows) - len(ok)}"]
    if ok:
        mean = statistics.mean(r["job_s"] for r in ok)
        out.append(f"estimated remaining: {fmt_dur(mean * (len(jobs) - len(rows)))} (from {len(ok)} finished jobs)")
    if alive and st.get("current") and st["state"] == "running":
        c = st["current"]
        out.append(f"now: #{c['n']} {c['model']} / {c['config']} - {st.get('phase')} "
                   f"({fmt_dur(time.time() - st.get('job_started', time.time()))})")
    if st and st.get("reason"):
        out.append(f"reason: {st['reason']}")
    late = time.time() - st.get("heartbeat", 0) if alive else 0
    if late >= HEARTBEAT_LATE_S:
        out.append(f"warning: no heartbeat for {fmt_dur(late)}, but the runner process (PID {st.get('pid')}) "
                   "is still there; if it stays like this, check the runner's window")
    if alive:
        cmd = control()
        if cmd["cmd"] != "run" and st["state"] == "running":
            out.append(f"requested: {cmd['cmd']}{' --now' if cmd.get('now') else ' after the current job'}")
    if show_jobs:
        out.append("")
        for j in jobs:
            r = results.get(j["id"])
            out.append(f"{j['n']:3d} {(r['status'] if r else '-'):12s} {j['model']} / {j['config']}")
    elif rows:
        out.append("")
        out.append("last results:")
        for r in sorted(rows, key=lambda r: r.get("finished", ""))[-6:]:
            out.append(f"  {r['model'][:34]:34s} {r['config']:12s} {r['status']:7s} "
                       f"vram+{r.get('vram_delta_mib', '-')}  decode {r.get('decode_tok_s', '-')} t/s"
                       + ("  NEAR VRAM LIMIT" if r.get("near_vram_limit") else ""))
    out.append("")
    out.append("commands: bench pause [--now] | bench resume | bench stop [--now] | bench status --jobs")
    return "\n".join(out), not alive


def default_grid():
    """The user's own (untracked) grid if present, otherwise the sample grid."""
    local = ROOT / "configs" / "quick.local.json"
    return str(local if local.exists() else ROOT / "configs" / "quick.json")


def cmd_run(a):
    log(f"grid: {a.grid}")
    grid = json.loads(Path(a.grid).read_text(encoding="utf-8"))
    keys = [k.strip() for k in a.models.split(",")] if a.models else grid.get("models", [])
    meta = model_catalog()
    missing = [k for k in keys if k not in meta]
    if not keys or missing:
        log(f"no models selected or unknown model keys: {missing}")
        return 2
    jobs = build_jobs(grid, keys, meta)
    if a.dry_run:
        for j in jobs:
            print(f"{j['n']:3d} {j['model']} / {j['config']}")
        print(f"{len(jobs)} jobs (dry run, nothing started)")
        return 0
    if runner_alive(read_json(STATUS)):
        log("another run is active; use `bench status`, or `bench stop` first")
        return 2
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    options = {k: getattr(a, k) for k in ("repeats", "gen_tokens", "prompt_lines", "load_timeout",
                                          "gen_timeout", "min_free_mib", "max_util", "busy_retry_s")}
    write_json(STATE / "runs" / run_id / "plan.json",
               {"grid": a.grid, "jobs": jobs, "options": options, "env": environment()})
    LATEST.write_text(run_id)
    return execute(run_id)


def cmd_resume(a):
    st = read_json(STATUS)
    if runner_alive(st):
        if a.from_job or a.redo_failed or a.run or a.allow_env_change:
            log("the run is still active; `bench stop` first, then resume with these options")
            return 2
        send("run")
        log("resume requested" if st["state"] == "paused" else "run is active; pending pause/stop cancelled")
        return 0
    run_id = a.run or (LATEST.read_text().strip() if LATEST.exists() else None)
    run_dir = STATE / "runs" / str(run_id)
    plan = read_json(run_dir / "plan.json")
    if not plan:
        log("nothing to resume")
        return 2
    plan["options"]["allow_env_change"] = a.allow_env_change
    write_json(run_dir / "plan.json", plan)
    if a.from_job:
        path = ROOT / "results" / f"sweep_{run_id}.jsonl"
        have = latest_results(path)
        for j in plan["jobs"]:
            if j["n"] >= a.from_job and j["id"] in have:
                append_row(path, {"job_id": j["id"], "status": "invalidated"})
    LATEST.write_text(run_id)
    return execute(run_id, redo_failed=a.redo_failed)


def cmd_evaluate(a):
    run_id = a.run or (LATEST.read_text().strip() if LATEST.exists() else None)
    path = ROOT / "results" / f"sweep_{run_id}.jsonl"
    if not run_id or not path.exists():
        log("no results to evaluate")
        return 2
    text = evaluate.report(evaluate.load_rows(path), run_id, a.in_tokens, a.out_tokens)
    out = ROOT / "report" / f"eval_{run_id}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text.split("\n## ", 2)[0])
    print("## " + text.split("\n## ", 2)[1])
    print(f"full report: {out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--grid", default=default_grid(),
                   help="grid file (default: configs/quick.local.json if present, else configs/quick.json)")
    r.add_argument("--models", help="comma separated model keys (default: the grid's list)")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--repeats", type=int, default=2)
    r.add_argument("--gen-tokens", type=int, default=200)
    r.add_argument("--prompt-lines", type=int, default=60)
    r.add_argument("--load-timeout", type=int, default=240)
    r.add_argument("--gen-timeout", type=int, default=180)
    r.add_argument("--min-free-mib", type=int, default=3500)
    r.add_argument("--max-util", type=int, default=30)
    r.add_argument("--busy-retry", dest="busy_retry_s", type=int, default=BUSY_RETRY_S,
                   help="seconds between automatic re-checks while paused for a busy GPU (0: wait for resume)")
    s = sub.add_parser("status")
    s.add_argument("--watch", action="store_true")
    s.add_argument("--jobs", action="store_true")
    for name in ("pause", "stop"):
        p = sub.add_parser(name)
        p.add_argument("--now", action="store_true")
    m = sub.add_parser("resume")
    m.add_argument("--run")
    m.add_argument("--from", dest="from_job", type=int)
    m.add_argument("--redo-failed", action="store_true")
    m.add_argument("--allow-env-change", action="store_true")
    e = sub.add_parser("evaluate", help="rank configurations of a finished sweep (offline)")
    e.add_argument("--run")
    e.add_argument("--in-tokens", type=int, default=2000)
    e.add_argument("--out-tokens", type=int, default=500)
    a = ap.parse_args(argv)

    if a.cmd == "evaluate":
        return cmd_evaluate(a)
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "resume":
        return cmd_resume(a)
    if a.cmd == "status":
        try:
            finished_reads = 0
            while True:
                text, finished = status_text(a.jobs)
                if a.watch:
                    os.system("cls" if os.name == "nt" else "clear")
                print(text, flush=True)
                finished_reads = finished_reads + 1 if finished else 0
                if not a.watch or finished_reads >= 2:  # one odd reading must not end the view
                    return 0
                time.sleep(3)
        except KeyboardInterrupt:
            return 0
    if not runner_alive(read_json(STATUS)):
        print("no active run")
        return 2
    send(a.cmd, a.now)
    print(f"{a.cmd} requested ({'now' if a.now else 'after the current job'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
