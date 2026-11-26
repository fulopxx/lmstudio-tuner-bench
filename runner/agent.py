"""Agent task runs: load one model, run a task set through the TypeScript harness, check the answers.

  bench agent run --model qwen3-8b [--tasks tasks/examples.json] [--repeats 1] [--context 8192]
  bench agent run --scripted replies.json      offline: scripted model replies, no GPU and no LM Studio

The harness (harness/run-tasks.ts) executes the tool loop and writes one JSONL trace per attempt; this module
loads and unloads the model, starts the harness, passes Ctrl+C on as a stop command and judges each attempt
from its trace with the task's declarative checks. Results: results/agent_<run>.jsonl, traces and sandboxes
below results/agent/<run>/. Only the model instance loaded here ("bench-agent") is unloaded.
"""
import argparse
import json
import shutil
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep  # noqa: E402
from smoke import LMS, StepError, sh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
IDENTIFIER = "bench-agent"
SCHEMA_VERSION = 1
STOP_GRACE_S = 20  # after a stop command, the harness gets this long before it is killed
CHECK_KEYS = ("answer_contains", "answer_contains_any", "tool_called", "tool_not_called", "mentions_failure")


def log(m):
    print(m, flush=True)


def load_settings(context):
    """Settings that measured well on the development machine: full offload, f16 KV, flash attention."""
    return {"context_length": context, "offload_ratio": 1, "flash_attention": True, "eval_batch_size": 2048,
            "physical_batch_size": 512, "parallel": 1, "offload_kv_cache_to_gpu": True, "unified_kv": True,
            "threads": 8, "kv_quant": None}


def read_events(trace_path):
    """Events of one trace; a broken last line (killed harness) is skipped."""
    events = []
    try:
        lines = Path(trace_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def evaluate_attempt(task, attempt, events):
    """Pass/fail of one attempt from its outcome and trace (the checks are declared in the task file)."""
    checks = task.get("checks", {})
    answer = (attempt.get("answer") or "").lower()
    called = [e.get("name") for e in events if e.get("event") == "tool_call" and e.get("parsed")]
    results = {}
    if "answer_contains" in checks:
        results["answer_contains"] = all(s.lower() in answer for s in checks["answer_contains"])
    if "answer_contains_any" in checks:
        results["answer_contains_any"] = any(s.lower() in answer for s in checks["answer_contains_any"])
    if "tool_called" in checks:
        results["tool_called"] = checks["tool_called"] in called
    if "tool_not_called" in checks:
        name = checks["tool_not_called"]
        results["tool_not_called"] = not called if name == "*" else name not in called
    if "mentions_failure" in checks:
        results["mentions_failure"] = any(s.lower() in answer for s in checks["mentions_failure"])
    ran = attempt.get("status") in ("done", "limit")
    return {"passed": ran and all(results.values()), "checks": results,
            "tools_called": called, "trace_complete": bool(events) and events[-1].get("event") == "task_end"}


def load_tasks(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise StepError("fail", f"{path}: schema_version must be {SCHEMA_VERSION}")
    for t in data["tasks"]:
        unknown = set(t.get("checks", {})) - set(CHECK_KEYS)
        if unknown:
            raise StepError("fail", f"task {t.get('id')}: unknown checks {sorted(unknown)}")
    return data


def run_harness(spec, timeout_s):
    """Starts the harness, streams its progress, sends stop on Ctrl+C; returns the RESULT summary."""
    p = subprocess.Popen([shutil.which("node") or "node", "run-tasks.ts"], cwd=HARNESS, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace")
    p.stdin.write(json.dumps(spec) + "\n")
    p.stdin.flush()
    lines, errors = [], []

    def pump(stream, sink, echo):
        for line in stream:
            sink.append(line.rstrip("\n"))
            if echo and line.strip() and not line.startswith("RESULT:"):
                log("  " + line.rstrip())

    readers = [threading.Thread(target=pump, args=(p.stdout, lines, True), daemon=True),
               threading.Thread(target=pump, args=(p.stderr, errors, False), daemon=True)]
    for r in readers:
        r.start()
    deadline = time.time() + timeout_s
    stop_sent_at = None
    try:
        while p.poll() is None:
            try:
                p.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
            if stop_sent_at is None and time.time() > deadline:
                log("time limit of the whole run reached: sending stop")
                stop_sent_at = send_stop(p)
            if stop_sent_at and p.poll() is None and time.time() - stop_sent_at > STOP_GRACE_S:
                log("harness did not stop in time: killing it")
                p.kill()
    except KeyboardInterrupt:
        log("Ctrl+C: asking the harness to stop (again to kill it)")
        send_stop(p)
        try:
            p.wait(timeout=STOP_GRACE_S)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            p.kill()
    for r in readers:
        r.join(timeout=5)
    for stream in (p.stdin, p.stdout, p.stderr):
        try:
            stream.close()
        except OSError:
            pass
    line = next((ln for ln in reversed(lines) if ln.startswith("RESULT:")), None)
    if not line:
        raise StepError("fail", "harness ended without a result: " + "\n".join(errors or lines)[-600:])
    result = json.loads(line[len("RESULT:"):])
    if "error" in result:
        raise StepError("fail", "harness: " + result["error"])
    return result


def send_stop(p):
    try:
        p.stdin.write(json.dumps({"cmd": "stop"}) + "\n")
        p.stdin.flush()
    except OSError:
        pass
    return time.time()


def machine_ready(min_free_mib, max_util):
    rc, ps = sh([LMS, "ps"], 30)
    if IDENTIFIER in ps:  # left over from a killed run: it is ours
        log(f"unloading '{IDENTIFIER}' left over from an earlier run")
        sh([LMS, "unload", IDENTIFIER], 60)
        time.sleep(2)
        rc, ps = sh([LMS, "ps"], 30)
    if "No models are currently loaded" not in ps:
        raise StepError("fail", "a model is loaded that this run did not load; unload it in LM Studio")
    samples = [sweep.gpu_state() for _ in range(3)]
    used, total = samples[-1][0], samples[-1][1]
    util = statistics.median(s[2] for s in samples)
    if total - used < min_free_mib or util > max_util:
        raise StepError("fail", f"GPU not idle: {total - used} MiB free, {util}% busy")


def cmd_run(a):
    data = load_tasks(a.tasks)
    tasks = data["tasks"]
    if a.only:
        wanted = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
        if not tasks:
            raise StepError("fail", f"no task matches --only {a.only}")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "results" / "agent" / run_id
    harness_tasks = [{k: v for k, v in t.items() if k != "checks"} for t in tasks]
    spec = {"schemaVersion": SCHEMA_VERSION, "run": run_id, "tasks": harness_tasks, "repeats": a.repeats,
            "limits": data.get("limits", {}), "temperature": a.temperature, "outDir": str(out_dir),
            "fixturesRoot": str((Path(a.tasks).resolve().parent / data.get("fixtures", "fixtures")))}
    meta = {"run": run_id, "tasks_file": str(a.tasks), "repeats": a.repeats, "temperature": a.temperature}
    loaded = False
    try:
        if a.scripted:
            spec["backend"] = {"type": "scripted",
                               "replies": json.loads(Path(a.scripted).read_text(encoding="utf-8"))}
            meta.update(model="scripted", backend="scripted")
        else:
            if not a.model:
                raise StepError("fail", "--model is required (or --scripted for an offline run)")
            machine_ready(a.min_free_mib, a.max_util)
            catalog = sweep.model_catalog()
            if a.model not in catalog:
                raise StepError("fail", f"unknown model key '{a.model}' (see `lms ls`)")
            log(f"loading {a.model} (context {a.context})")
            loaded = True  # a failed load may still leave the instance behind
            info = sweep.sdk_load(catalog[a.model]["path"], load_settings(a.context), a.load_timeout, IDENTIFIER)
            if info.get("mismatches"):
                raise StepError("fail", "load settings not applied: " + "; ".join(info["mismatches"]))
            spec["backend"] = {"type": "lmstudio", "identifier": IDENTIFIER}
            meta.update(model=a.model, backend="lmstudio", app_version=info.get("app"), context=a.context,
                        env=sweep.environment())
        log(f"run {run_id}: {len(tasks)} task(s) x {a.repeats}")
        summary = run_harness(spec, a.run_timeout)
    finally:
        if loaded:
            sh([LMS, "unload", IDENTIFIER], 60)

    by_id = {t["id"]: t for t in tasks}
    rows = []
    results_file = ROOT / "results" / f"agent_{run_id}.jsonl"
    for at in summary["attempts"]:
        verdict = evaluate_attempt(by_id[at["task"]], at, read_events(at["trace"])) if at.get("trace") else \
            {"passed": False, "checks": {}, "tools_called": [], "trace_complete": False}
        row = {"schema_version": SCHEMA_VERSION, **meta, "task": at["task"], "attempt": at["attempt"],
               "status": at["status"], **verdict, "answer": at.get("answer"), "rounds": at.get("rounds"),
               "tool_calls": at.get("toolCalls"), "limits_hit": at.get("limitsHit"), "seconds": at.get("seconds"),
               "error": at.get("error"), "trace": at.get("trace"), "sandbox": at.get("sandbox")}
        sweep.append_row(results_file, row)
        rows.append(row)
    print_summary(rows, summary.get("stopped"))
    log(f"results: {results_file}")
    return 0


def print_summary(rows, stopped):
    log("")
    log(f"{'task':<22} {'try':>3}  {'status':<8} {'pass':<5} {'rounds':>6} {'tools':>5}  checks")
    for r in rows:
        failed = [k for k, v in r["checks"].items() if not v]
        log(f"{r['task']:<22} {r['attempt']:>3}  {r['status']:<8} {'yes' if r['passed'] else 'no':<5} "
            f"{r['rounds'] or 0:>6} {r['tool_calls'] or 0:>5}  {'failed: ' + ', '.join(failed) if failed else 'ok'}")
    passed = sum(r["passed"] for r in rows)
    log(f"passed {passed}/{len(rows)}" + (" (stopped early)" if stopped else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bench agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a task set on one model through the harness")
    r.add_argument("--model", help="model key from `lms ls`")
    r.add_argument("--tasks", default=str(ROOT / "tasks" / "examples.json"))
    r.add_argument("--only", help="comma separated task ids")
    r.add_argument("--repeats", type=int, default=1)
    r.add_argument("--context", type=int, default=8192)
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--load-timeout", type=int, default=240)
    r.add_argument("--run-timeout", type=int, default=3600, help="seconds for the whole task set")
    r.add_argument("--min-free-mib", type=int, default=3500)
    r.add_argument("--max-util", type=int, default=30)
    r.add_argument("--scripted", help="JSON file with scripted replies per task id (offline, no model)")
    a = ap.parse_args(argv)
    try:
        return cmd_run(a)
    except StepError as e:
        log(f"agent run failed: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
