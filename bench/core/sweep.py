#!/usr/bin/env python3
"""Speed/memory sweep over (model x load configuration) with live status, pause, stop and resume.

  bench run --grid configs/quick.json [--models a,b] [--dry-run]
  bench status [--watch] [--jobs]
  bench pause [--now]      wait; GPU is freed (model unloaded, a server started by the run stopped)
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
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import evaluate, machine, progress, results, runstate, smoke
from . import models as registry
from .progress import CoreError
from .smoke import LMS, StepError, sh

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"
IDENTIFIER = "bench-sweep"  # the only model instance this runner loads and removes
ACTIVE = runstate.ACTIVE_STATES
BUSY_RETRY_S = 90  # re-check interval while paused because the machine was not ready
HEARTBEAT_LATE_S = runstate.HEARTBEAT_LATE_S


def latest_path():
    """state/latest.txt: the latest sweep (the one `resume`, `status` and `evaluate` use by default)."""
    return runstate.STATE / "latest.txt"


def latest_run():
    path = latest_path()
    return path.read_text().strip() if path.exists() else None


def stamp(m):
    return f"{datetime.now():%H:%M:%S} {m}"


def log(m):
    progress.emit(stamp(m))


# ---------------------------------------------------------------- files, control channel (per run, see runstate)
write_json, read_json = runstate.write_json, runstate.read_json
process_created, runner_alive = runstate.process_created, runstate.runner_alive
send, control = runstate.send, runstate.control


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
        for r in results.read_rows(path):
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


def runtime_warning(runtime, jobs):
    """Text if the selected llama.cpp runtime has no GPU backend although jobs offload to the GPU, else None."""
    if re.search(r"(?i)cuda|vulkan|rocm|metal", runtime):
        return None
    if not any(j["settings"].get("offload_ratio", 0) > 0 for j in jobs):
        return None
    return (f"the selected GGUF runtime '{runtime}' has no GPU support, but the grid offloads to the GPU; "
            "check `lms runtime ls`")


def sdk_load(model_path, settings, timeout, identifier=IDENTIFIER):
    """Load through the Node helper (harness/load-model.ts). The model stays loaded after it exits."""
    request = {"model": model_path, "identifier": identifier, "settings": settings, "timeoutMs": timeout * 1000}
    try:
        p = subprocess.run([shutil.which("node") or "node", "load-model.ts"], cwd=HARNESS, input=json.dumps(request),
                           env=machine.node_env(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout + 30)
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


# ---------------------------------------------------------------- runner
class Runner:
    def __init__(self, run_id, plan, status):
        self.run_id, self.plan, self.status = run_id, plan, status
        self.o = plan["options"]
        self.started_server = False
        self.instance = None
        self._last_check = 0.0

    def checkpoint(self, in_job=True):
        c = control(self.run_id)
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
            row["app_version"] = loaded.get("app")
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
        seen = control(self.run_id).get("ts")
        next_check = time.time() + retry

        def note(text):
            return f"{text} (checking again every {retry} s)" if retry else text

        self.status.update(state="paused", phase="paused", reason=note(reason))
        log(f"PAUSED: {note(reason)}\n         `bench resume` to continue, `bench stop` to exit.")
        while True:
            c = control(self.run_id)
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
                    if control(self.run_id).get("ts") != c.get("ts"):
                        continue  # a new command arrived during the checks
                    send(self.run_id, "run")
                    self.status.update(state="running", reason="")
                    log("RESUMED" if c["cmd"] == "run" else "RESUMED automatically")
                    return "run"
                except (Blocked, StepError) as e:
                    if c["cmd"] == "run" and control(self.run_id).get("ts") == c.get("ts"):
                        send(self.run_id, "pause")
                        seen = control(self.run_id).get("ts")
                    next_check = time.time() + retry
                    self.status.update(reason=note(str(e)))
                    log(f"cannot resume yet: {e}")
            time.sleep(1)


def execute(run_id, redo_failed=False):
    """Runs the jobs of a planned sweep in this process. The caller holds the GPU lock (runstate.acquire)."""
    run_dir = runstate.run_dir(run_id)
    plan = read_json(run_dir / "plan.json")
    if not plan:
        log(f"no plan for run {run_id}")
        return 2
    results_path = ROOT / "results" / f"sweep_{run_id}.jsonl"
    report_path = ROOT / "report" / f"sweep_{run_id}.md"
    jobs = plan["jobs"]
    runstate.init_files(run_id)
    status = runstate.Status(run_id, {"kind": "sweep", "state": "starting", "phase": "starting", "reason": "",
                                      "total": len(jobs), "started": time.time()})
    runner = Runner(run_id, plan, status)
    final, reason, code, consecutive_timeouts = "aborted", "", 3, 0
    try:
        env = environment()
        fingerprint = machine.fingerprint()
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
        warning = runtime_warning(env["runtime"], todo)
        if warning:
            log(f"WARNING: {warning}")
        status.update(state="running", warning=warning)
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
                    send(run_id, "pause")
                    if runner.wait_paused(str(e), auto=True) == "stop":
                        raise Interrupted("stop")
            append_row(results_path, results.envelope("sweep", run_id, row, fingerprint))
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


# ---------------------------------------------------------------- operations (called by the CLI, later by the API)
def run_status(show_jobs=False):
    """State of the active run (sweep or agent), otherwise of the latest sweep, as data; `finished` is true when no
    runner is alive."""
    lock = runstate.active()
    run_id = lock["run"] if lock else latest_run()
    if not run_id:
        return {"run": None, "kind": None, "finished": True}
    st = runstate.read_status(run_id)
    alive = runner_alive(st)
    now = time.time()
    out = {"run": run_id, "kind": (lock or st or {}).get("kind", "sweep"), "state": (st or {}).get("state", "?"),
           "alive": alive, "gone": (st or {}).get("state") in ACTIVE and not alive, "current": None,
           "reason": (st or {}).get("reason"), "warning": (st or {}).get("warning"), "heartbeat_late_s": None,
           "pid": (st or {}).get("pid"), "requested": None, "finished": not alive}
    late = now - st.get("heartbeat", 0) if alive else 0
    if late >= HEARTBEAT_LATE_S:
        out["heartbeat_late_s"] = late
    if out["kind"] == "agent":  # the attempts of an agent run are counted with D2b's progress data
        c = (st or {}).get("current") if alive else None
        out.update(total=(st or {}).get("total"), current=c and {
            "n": c["n"], "model": c["model"], "phase": st.get("phase"), "elapsed_s": now - st.get("job_started", now)})
        return out
    plan = read_json(runstate.run_dir(run_id) / "plan.json", {"jobs": []})
    results = latest_results(ROOT / "results" / f"sweep_{run_id}.jsonl")
    jobs = plan["jobs"]
    rows = [results[j["id"]] for j in jobs if j["id"] in results and results[j["id"]]["status"] != "invalidated"]
    ok = [r for r in rows if r["status"] == "ok"]
    out.update(total=len(jobs), finished_jobs=len(rows), failed=len(rows) - len(ok), ok_jobs=len(ok),
               remaining_s=statistics.mean(r["job_s"] for r in ok) * (len(jobs) - len(rows)) if ok else None)
    if alive and st.get("current") and st["state"] == "running":
        c = st["current"]
        out["current"] = {"n": c["n"], "model": c["model"], "config": c["config"], "phase": st.get("phase"),
                          "elapsed_s": now - st.get("job_started", now)}
    if alive:
        cmd = control(run_id)
        if cmd["cmd"] != "run" and st["state"] == "running":
            out["requested"] = {"cmd": cmd["cmd"], "now": bool(cmd.get("now"))}
    if show_jobs:
        out["jobs"] = [{"n": j["n"], "model": j["model"], "config": j["config"],
                        "status": results[j["id"]]["status"] if j["id"] in results else None} for j in jobs]
    else:
        out["last_results"] = sorted(rows, key=lambda r: r.get("finished", ""))[-6:]
    return out


def default_grid():
    """The user's own (untracked) grid if present, otherwise the sample grid."""
    local = ROOT / "configs" / "quick.local.json"
    return str(local if local.exists() else ROOT / "configs" / "quick.json")


def plan_run(grid_path, models=None, where=None):
    """The jobs a run would measure, without starting anything; raises CoreError for unknown models."""
    grid = json.loads(Path(grid_path).read_text(encoding="utf-8"))
    keys = [k.strip() for k in models.split(",")] if models else grid.get("models", [])
    if where:  # CR-24: the given models, or every model of the registry, that match the capability filter
        keys = registry.select_fresh(where, [k.strip() for k in models.split(",")] if models else None)
    meta = model_catalog()
    missing = [k for k in keys if k not in meta]
    if not keys or missing:
        raise CoreError(f"no models selected or unknown model keys: {missing}")
    jobs = build_jobs(grid, keys, meta)
    return {"grid": grid_path, "jobs": jobs, "warning": runtime_warning(environment()["runtime"], jobs)}


RUN_OPTIONS = ("repeats", "gen_tokens", "prompt_lines", "load_timeout", "gen_timeout", "min_free_mib", "max_util",
               "busy_retry_s")


def start_run(grid_path, models, options, where=None):
    """Starts a sweep and runs it to the end in this process; progress goes to the progress sink. Refuses to start
    while another sweep or agent run holds the GPU (IF-13)."""
    jobs = plan_run(grid_path, models, where)["jobs"]
    run_id = runstate.new_run_id()
    runstate.acquire(run_id, "sweep")
    try:
        runstate.new_run_dir(run_id)
        write_json(runstate.run_dir(run_id) / "plan.json",
                   {"grid": grid_path, "jobs": jobs, "options": {k: options[k] for k in RUN_OPTIONS},
                    "env": environment()})
        latest_path().write_text(run_id)
        return {"run": run_id, "exit_code": execute(run_id)}
    finally:
        runstate.release(run_id)


def resume_run(run=None, from_job=None, redo_failed=False, allow_env_change=False):
    """Resumes a run: asks a living runner to continue, or restarts a stopped one from disk in this process."""
    lock = runstate.active()
    if lock:
        if lock.get("kind") != "sweep" or (run and run != lock["run"]):
            raise CoreError(f"another run is active: {lock.get('kind')} run {lock['run']}; wait for it or stop it first")
        if from_job or redo_failed or allow_env_change:
            raise CoreError("the run is still active; `bench stop` first, then resume with these options")
        st = runstate.read_status(lock["run"]) or {}
        send(lock["run"], "run")
        return {"run": lock["run"], "exit_code": 0, "message":
                "resume requested" if st.get("state") == "paused" else "run is active; pending pause/stop cancelled"}
    run_id = run or latest_run()
    run_dir = runstate.run_dir(run_id)
    plan = read_json(run_dir / "plan.json")
    if not plan:
        raise CoreError("nothing to resume")
    runstate.acquire(run_id, "sweep")
    try:
        plan["options"]["allow_env_change"] = allow_env_change
        write_json(run_dir / "plan.json", plan)
        if from_job:
            path = ROOT / "results" / f"sweep_{run_id}.jsonl"
            have = latest_results(path)
            for j in plan["jobs"]:
                if j["n"] >= from_job and j["id"] in have:
                    append_row(path, results.envelope("sweep", run_id, {"job_id": j["id"], "status": "invalidated"},
                                                      machine.fingerprint()))
        latest_path().write_text(run_id)
        return {"run": run_id, "exit_code": execute(run_id, redo_failed=redo_failed), "message": None}
    finally:
        runstate.release(run_id)


def request_control(cmd, now=False):
    """Asks the running sweep to pause or stop."""
    lock = runstate.active()
    if not lock or not runner_alive(runstate.read_status(lock["run"])):
        raise CoreError("no active run")
    if lock.get("kind") != "sweep":
        raise CoreError(f"agent run {lock['run']} is active; it cannot be paused, and stopping it from here comes "
                        "later: press Ctrl+C in its window")
    send(lock["run"], cmd, now)
    return {"run": lock["run"], "cmd": cmd, "now": now}


def evaluate_run(run=None, in_tokens=2000, out_tokens=500):
    """Writes the evaluation report of a sweep; returns its text and path."""
    run_id = run or latest_run()
    path = ROOT / "results" / f"sweep_{run_id}.jsonl"
    if not run_id or not path.exists():
        raise CoreError("no results to evaluate")
    text = evaluate.report(evaluate.load_rows(path), run_id, in_tokens, out_tokens)
    out = ROOT / "report" / f"eval_{run_id}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return {"run": run_id, "text": text, "path": out}
