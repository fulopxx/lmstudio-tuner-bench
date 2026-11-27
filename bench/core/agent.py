"""Agent task runs: load one model, run a task set through the TypeScript harness, check and categorize the attempts.

  bench agent run --model qwen3-8b [--tasks tasks/examples.json] [--repeats 1] [--context 8192]
  bench agent run --models a,b,c [--tasks tasks/m1.json] [--repeats 5]
  bench agent run --scripted replies.json      offline: scripted model replies, no GPU and no LM Studio
  bench agent report [--run <id>]               pass rates, categories, chains (offline)
  bench agent show <run> <task>-<n>             the steps of one attempt with the evidence (offline)

The harness (harness/run-tasks.ts) executes the tool loop and writes one JSONL trace per attempt; this module loads
and unloads the model, starts the harness, passes Ctrl+C on as a stop command, judges each attempt from its trace with
the task's checks and expected calls, and gives every failed attempt a category (runner/failures.py). Results:
results/agent_<run>.jsonl; traces, sandboxes and a copy of the task file below results/agent/<run>/. Only the model
instance loaded here ("bench-agent") is unloaded.
"""
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import failures, progress, sweep
from .smoke import LMS, StepError, sh

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"
IDENTIFIER = "bench-agent"
TASKS_SCHEMA_VERSION = 2  # the task file (FA-12)
SPEC_SCHEMA_VERSION = 2  # the run spec sent to the harness
SAMPLING_FILE = ROOT / "configs" / "sampling.json"
STOP_GRACE_S = 20  # after a stop command, the harness gets this long before it is killed
BUILTIN_TOOLS = ("read_file",)
CHECK_KEYS = ("answer_contains", "answer_contains_any", "answer_not_contains", "tool_called", "tool_not_called",
              "mentions_failure")
TASK_KEYS = ("id", "comment", "chain_length", "prompt", "system", "fixtures", "tools", "limits", "expected_calls",
             "forbidden_tools",
             "checks", "accept_limit", "no_tool_needed", "max_tool_calls", "loop_threshold")
HARNESS_TASK_KEYS = ("id", "prompt", "system", "fixtures", "tools", "limits")


def log(m):
    progress.emit(m)


def load_settings(context):
    """Settings that measured well on the development machine: full offload, f16 KV, flash attention."""
    return {"context_length": context, "offload_ratio": 1, "flash_attention": True, "eval_batch_size": 2048,
            "physical_batch_size": 512, "parallel": 1, "offload_kv_cache_to_gpu": True, "unified_kv": True,
            "threads": 8, "kv_quant": None}


# ---------------------------------------------------------------- task file and sampling profile

def load_tasks(path):
    """Reads and checks a task file (format v2); returns the data and its hash."""
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema_version") != TASKS_SCHEMA_VERSION:
        raise StepError("fail", f"{path}: schema_version must be {TASKS_SCHEMA_VERSION}")
    toolsets = data.get("toolsets", {})
    problems = []
    ids = set()
    for t in data.get("tasks", []):
        tid = t.get("id")
        if tid in ids:
            problems.append(f"task id '{tid}' is not unique")
        ids.add(tid)
        problems += [f"task {tid}: unknown key '{k}'" for k in t if k not in TASK_KEYS]
        problems += [f"task {tid}: unknown check '{k}'" for k in t.get("checks", {}) if k not in CHECK_KEYS]
        offered = set(t.get("tools", []))
        for name in offered:
            if name not in BUILTIN_TOOLS and name not in toolsets:
                problems.append(f"task {tid}: tool '{name}' is not declared in toolsets")
        for e in t.get("expected_calls", []):
            if e.get("name") not in offered:
                problems.append(f"task {tid}: expected call to '{e.get('name')}', which is not offered")
            for arg, m in e.get("arguments", {}).items():
                if not isinstance(m, dict) or len(m) != 1 or next(iter(m)) not in ("equals", "one_of", "any"):
                    problems.append(f"task {tid}: matcher of '{arg}' must be one of equals, one_of, any")
        groups = t.get("checks", {}).get("answer_contains_any")
        if groups is not None and not (all(isinstance(s, str) for s in groups) or
                                       all(isinstance(g, list) and g and all(isinstance(s, str) for s in g)
                                           for g in groups)):
            problems.append(f"task {tid}: answer_contains_any must be a list of strings or a list of string lists")
        if t.get("no_tool_needed") and t.get("expected_calls"):
            problems.append(f"task {tid}: no_tool_needed together with expected_calls")
    if not ids:
        problems.append("no tasks")
    if problems:
        raise StepError("fail", f"{path}: " + "; ".join(problems))
    return data, hashlib.sha256(raw).hexdigest()[:16]


def sampling_for(model, temperature=None, path=SAMPLING_FILE):
    """The sampling profile of a model key (FA-20); `temperature` overrides only the temperature."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    profile = next((p for p in data["profiles"] if re.search(p["match"], model or "", re.I)), data["fallback"])
    s = {"temperature": profile["temperature"], "topP": profile.get("top_p"), "topK": profile.get("top_k"),
         "minP": profile.get("min_p"), "repeatPenalty": profile.get("repeat_penalty"),
         "source": f"{profile['id']}: {profile.get('source', '')}"}
    if temperature is not None:
        s["temperature"] = temperature
        s["source"] += " (temperature overridden)"
    return {k: v for k, v in s.items() if v is not None}


# ---------------------------------------------------------------- traces and judging

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


def answer_groups(value):
    """`answer_contains_any` is one group of alternatives (a list of strings) or several groups (a list of lists);
    every group must match at least one of its strings."""
    return value if value and all(isinstance(g, list) for g in value) else [value]


def evaluate_attempt(task, attempt, events):
    """Pass/fail of one attempt from its outcome and trace: checks, expected calls (ordered subsequence, extra calls
    allowed, FA-04), forbidden tools, call budget. Status `limit` fails unless the task accepts it (FA-07)."""
    checks = task.get("checks", {})
    answer = (attempt.get("answer") or "").lower()
    calls = failures.parsed_calls(events)
    called = [c.get("name") for c in calls]
    results = {}
    if "answer_contains" in checks:
        results["answer_contains"] = all(s.lower() in answer for s in checks["answer_contains"])
    if "answer_contains_any" in checks:
        results["answer_contains_any"] = all(any(s.lower() in answer for s in g)
                                             for g in answer_groups(checks["answer_contains_any"]))
    if "answer_not_contains" in checks:
        results["answer_not_contains"] = not any(s.lower() in answer for s in checks["answer_not_contains"])
    if "mentions_failure" in checks:
        results["mentions_failure"] = any(s.lower() in answer for s in checks["mentions_failure"])
    if "tool_called" in checks:
        results["tool_called"] = checks["tool_called"] in called
    if "tool_not_called" in checks:
        name = checks["tool_not_called"]
        results["tool_not_called"] = not called if name == "*" else name not in called
    if task.get("no_tool_needed"):
        results["no_tool_called"] = not called
    if task.get("expected_calls"):
        done, _ = failures.subsequence_prefix(task["expected_calls"], calls)
        results["expected_calls"] = done == len(task["expected_calls"])
    if task.get("forbidden_tools"):
        results["forbidden_tools"] = not set(called) & set(task["forbidden_tools"])
    if task.get("max_tool_calls") is not None:
        results["max_tool_calls"] = len(calls) <= task["max_tool_calls"]
    status = attempt.get("status")
    ran = status == "done" or (status == "limit" and bool(task.get("accept_limit")))
    return {"passed": ran and all(results.values()), "checks": results, "tools_called": called,
            "trace_complete": bool(events) and events[-1].get("event") == "task_end"}


def attempts_from_traces(out_dir, tasks, repeats):
    """FA-41: rebuilds the attempt list from the traces when the harness gave no result line."""
    attempts = []
    for t in tasks:
        for n in range(1, repeats + 1):
            path = Path(out_dir) / "traces" / f"{t['id']}-{n}.jsonl"
            if not path.is_file():
                attempts.append({"task": t["id"], "attempt": n, "status": "skipped"})
                continue
            events = read_events(path)
            end = next((e for e in reversed(events) if e.get("event") == "task_end"), None)
            row = {"task": t["id"], "attempt": n, "trace": str(path),
                   "sandbox": str(Path(out_dir) / "sandbox" / f"{t['id']}-{n}")}
            if end:
                row.update(status=end.get("status"), answer=end.get("answer"), rounds=end.get("rounds"),
                           toolCalls=end.get("toolCalls"), limitsHit=end.get("limitsHit"), seconds=end.get("seconds"),
                           error=end.get("error"))
            else:
                row.update(status="error", error="trace ended without task_end (harness stopped)")
            attempts.append(row)
    return attempts


# ---------------------------------------------------------------- harness process

def send_stop(p):
    try:
        p.stdin.write(json.dumps({"cmd": "stop"}) + "\n")
        p.stdin.flush()
    except OSError:
        pass
    return time.time()


def harness_problem():
    """Why the harness cannot start here (no Node.js, or its packages are not installed), or None."""
    if not shutil.which("node"):
        return "Node.js was not found on PATH (needed for the agent harness)"
    if not (HARNESS / "node_modules" / "@lmstudio" / "sdk").is_dir():
        return "the harness packages are not installed: run `npm.cmd ci --ignore-scripts` in harness\\"
    return None


def run_harness(spec, timeout_s):
    """Starts the harness, streams its progress, sends stop on Ctrl+C. Returns the RESULT summary, or None when the
    harness ended without one (killed, crashed); raises if the harness reported an unusable spec."""
    p = subprocess.Popen([shutil.which("node") or "node", "run-tasks.ts"], cwd=HARNESS, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace")
    try:
        p.stdin.write(json.dumps(spec) + "\n")
        p.stdin.flush()
    except OSError:  # the harness ended before reading its spec; its stderr is reported below
        pass
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
        log("harness ended without a result: rebuilding the attempts from the traces. " +
            "\n".join(errors or lines)[-300:])
        return None
    result = json.loads(line[len("RESULT:"):])
    if "error" in result:
        raise StepError("fail", "harness: " + result["error"])
    return result


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


# ---------------------------------------------------------------- the run command

def model_slug(model):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def run_timeout(a, data, tasks):
    """FA-42: unless given, the time for the whole task set follows from tasks, repeats and the attempt limit."""
    if a.run_timeout:
        return a.run_timeout
    default_wall = data.get("limits", {}).get("wallTimeMs", 180_000)
    per_attempt = [t.get("limits", {}).get("wallTimeMs", default_wall) / 1000 + 5 for t in tasks]
    return int(sum(per_attempt) * a.repeats + 120)


def run_model(a, model, data, task_hash, tasks, run_id, run_dir, timeout_s):
    """One model of a run: load, harness, unload. Returns (attempts, summary or None, meta)."""
    out_dir = run_dir / model_slug(model)
    out_dir.mkdir(parents=True, exist_ok=True)
    used_tools = {n for t in tasks for n in t.get("tools", [])}
    sampling = sampling_for(model, a.temperature)
    spec = {"schemaVersion": SPEC_SCHEMA_VERSION, "run": run_id,
            "tools": {k: v for k, v in data.get("toolsets", {}).items() if k in used_tools},
            "tasks": [{k: v for k, v in t.items() if k in HARNESS_TASK_KEYS} for t in tasks],
            "repeats": a.repeats, "limits": data.get("limits", {}), "sampling": sampling, "outDir": str(out_dir),
            "fixturesRoot": str((Path(a.tasks).resolve().parent / data.get("fixtures", "fixtures"))),
            "meta": {"model": model, "contextLength": None if a.scripted else a.context,
                     "taskFile": str(a.tasks), "taskFileHash": task_hash}}
    meta = {"run": run_id, "model": model, "tasks_file": str(a.tasks), "tasks_hash": task_hash, "repeats": a.repeats,
            "sampling": sampling, "taxonomy_version": failures.TAXONOMY_VERSION}
    loaded = False
    try:
        if a.scripted:
            spec["backend"] = {"type": "scripted",
                               "replies": json.loads(Path(a.scripted).read_text(encoding="utf-8"))}
            meta["backend"] = "scripted"
        else:
            machine_ready(a.min_free_mib, a.max_util)
            catalog = sweep.model_catalog()
            if model not in catalog:
                raise StepError("fail", f"unknown model key '{model}' (see `lms ls`)")
            log(f"loading {model} (context {a.context})")
            loaded = True  # a failed load may still leave the instance behind
            info = sweep.sdk_load(catalog[model]["path"], load_settings(a.context), a.load_timeout, IDENTIFIER)
            if info.get("mismatches"):
                raise StepError("fail", "load settings not applied: " + "; ".join(info["mismatches"]))
            spec["backend"] = {"type": "lmstudio", "identifier": IDENTIFIER}
            meta.update(backend="lmstudio", app_version=info.get("app"), context=a.context, env=sweep.environment())
        log(f"run {run_id}, {model}: {len(tasks)} task(s) x {a.repeats}, sampling {sampling['source']}")
        summary = run_harness(spec, timeout_s)
    finally:
        if loaded:
            sh([LMS, "unload", IDENTIFIER], 60)
    attempts = summary["attempts"] if summary else attempts_from_traces(out_dir, tasks, a.repeats)
    return attempts, summary, meta


def run_tasks(a, on_model_done=None):
    """Runs a task set on the models of `a` (an options object with the fields of `bench agent run`). After the
    attempts of a model are judged, on_model_done(model, rows, stopped) is called. Returns the run id, the results
    file and the rows."""
    data, task_hash = load_tasks(a.tasks)
    problem = harness_problem()
    if problem:
        raise StepError("fail", problem)
    tasks = data["tasks"]
    if a.only:
        wanted = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
        if not tasks:
            raise StepError("fail", f"no task matches --only {a.only}")
    if a.scripted:
        models = ["scripted"]
    else:
        models = [m.strip() for m in (a.models or a.model or "").split(",") if m.strip()]
        if not models:
            raise StepError("fail", "--model or --models is required (or --scripted for an offline run)")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / "results" / "agent" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.tasks, run_dir / "tasks.json")  # FA-42: the run can be re-evaluated later
    timeout_s = run_timeout(a, data, tasks)
    by_id = {t["id"]: t for t in tasks}
    results_file = ROOT / "results" / f"agent_{run_id}.jsonl"
    all_rows = []
    for model in models:
        try:
            attempts, summary, meta = run_model(a, model, data, task_hash, tasks, run_id, run_dir, timeout_s)
        except StepError as e:  # FA-40: record the model's error and go on with the next model
            log(f"{model}: {e}")
            row = {"schema_version": TASKS_SCHEMA_VERSION, "run": run_id, "model": model, "task": "*", "attempt": 0,
                   "status": "error", "passed": False, "primary": "infra_error", "subcode": "harness_error",
                   "error": str(e), "taxonomy_version": failures.TAXONOMY_VERSION}
            sweep.append_row(results_file, row)
            all_rows.append(row)
            continue
        rows = []
        for at in attempts:
            task = by_id[at["task"]]
            events = read_events(at["trace"]) if at.get("trace") else []
            verdict = evaluate_attempt(task, at, events)
            category = failures.classify(task, at, events, verdict["passed"])
            row = {"schema_version": TASKS_SCHEMA_VERSION, **meta, "task": at["task"], "attempt": at["attempt"],
                   "status": at["status"], **verdict, **category, "answer": at.get("answer"),
                   "rounds": at.get("rounds"), "tool_calls": at.get("toolCalls"), "limits_hit": at.get("limitsHit"),
                   "seconds": at.get("seconds"), "error": at.get("error"), "trace": at.get("trace"),
                   "sandbox": at.get("sandbox"), "rebuilt_from_traces": summary is None}
            sweep.append_row(results_file, row)
            rows.append(row)
        if on_model_done:
            on_model_done(model, rows, summary.get("stopped") if summary else True)
        all_rows += rows
    return {"run": run_id, "results_file": results_file, "rows": all_rows}


# ---------------------------------------------------------------- report and show

def report(runs=None, tasks_file=None, k=5, reliable=0.8):
    """Recomputes verdicts and categories of one or more runs from their traces and writes the report (Markdown
    and JSON); returns its text and path."""
    from . import agent_report
    run_ids = runs or [agent_report.latest_run()]
    rows, tasks, meta = [], {}, {}
    for rid in run_ids:
        r, t = agent_report.load_rows(rid)
        rows += r
        tasks.update(t)
        if r:
            meta.setdefault("tasks_hash", r[0].get("tasks_hash"))
    if tasks_file:  # re-judge with a newer task file, e.g. after fixing a check; the traces stay as recorded
        data, digest = load_tasks(tasks_file)
        tasks = {t["id"]: t for t in data["tasks"]}
        meta.update(tasks_hash=digest, rejudged_with=str(tasks_file))
    rows = agent_report.rejudge(rows, tasks, read_events, evaluate_attempt)
    models = agent_report.summarize(rows, tasks, k=k, reliable=reliable)
    path = agent_report.write(run_ids, models, meta)
    return {"runs": run_ids, "text": path.read_text(encoding="utf-8"), "path": path}


def show_attempt(run, attempt, model=None):
    """FA-47: one attempt re-judged from its trace, with the events of the trace; `mark` is the sequence number of
    the event that decided its category."""
    from . import agent_report
    rows, tasks = agent_report.load_rows(run)
    task_id, _, number = attempt.rpartition("-")
    if not task_id or not number.isdigit():
        raise StepError("fail", "give the attempt as <task>-<number>, e.g. chain-3a-2")
    found = [r for r in rows if r.get("task") == task_id and r.get("attempt") == int(number)
             and (not model or r.get("model") == model)]
    if not found:
        raise StepError("fail", f"no attempt {attempt} in run {run}" + (f" for {model}" if model else ""))
    if len(found) > 1:
        raise StepError("fail", "several models ran this attempt; choose one with --model: "
                        + ", ".join(r.get("model") for r in found))
    row = agent_report.rejudge(found, tasks, read_events, evaluate_attempt)[0]
    return {"attempt": attempt, "row": row, "mark": (row.get("evidence") or {}).get("seq"),
            "events": read_events(row["trace"])}
