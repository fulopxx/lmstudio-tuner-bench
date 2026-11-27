"""The `bench` command line: argument parsing and output formatting only; every result comes from bench.core.

  bench run --grid configs/quick.json [--models a,b] [--dry-run]
  bench status [--watch] [--jobs]
  bench pause [--now]      wait; GPU is freed (model unloaded, a server started by the run stopped)
  bench resume             continue (same process if it is paused, otherwise restart from disk)
  bench resume --from 12   redo job 12 and everything after it
  bench resume --redo-failed
  bench stop [--now]       exit; can be resumed later, also after a reboot
  bench evaluate [--run]   rank the configurations of a finished sweep (offline)
  bench check              the machine check of a run, without measuring (exit code 1 if a run could not start)
  bench runs               every sweep and agent run with its state
  bench close <run>        mark an unfinished run as closed; it stays readable, it is never resumed
  bench agent run | report | show
  bench models refresh | list [--new] [--refresh] [--where]   the model registry (installed models, capability tags)

Exit codes of run and resume: 0 done or stopped by the user, 3 aborted, 2 unusable arguments.

--json (IF-01): every command that gives a result prints exactly one JSON document on standard output: the data of the
core function with `schema_version` at the top level, or {"schema_version": 1, "error": {"message", "code"}} with the
same exit code as without --json. Progress lines then go to standard error.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from bench.core import agent, check, progress, runs, sweep
from bench.core import models as registry
from bench.core.progress import CoreError
from bench.core.smoke import StepError


JSON_SCHEMA_VERSION = 1  # format of the --json output; part of every document


def say(text):
    print(text, flush=True)


def _plain(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def to_json(data):
    return json.dumps({"schema_version": JSON_SCHEMA_VERSION, **data}, ensure_ascii=False, indent=1, default=_plain)


def out_json(data, code=0):
    print(to_json(data), flush=True)
    return code


def error_json(message, code):
    return out_json({"error": {"message": str(message), "code": code}}, code)


def json_mode(a):
    """With --json the progress lines go to standard error, so standard output holds only the JSON document."""
    if getattr(a, "json", False):
        progress.set_sink(lambda text: print(text, file=sys.stderr, flush=True))
        return True
    return False


def fmt_dur(s):
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


WHERE_HELP = ("capability filter on the model registry, comma separated terms that all must hold: name (true), !name "
              "(false), name=value; e.g. tool_use,!vision or architecture=qwen3. Selects from --models if given, "
              "otherwise from every registered model")


# ---------------------------------------------------------------- sweep commands
def status_text(st, show_jobs):
    """Formats sweep.run_status()."""
    if not st["run"]:
        return "no run yet"
    if st["kind"] == "agent":
        state = "NOT RUNNING (process gone)" if st["gone"] else st["state"]
        out = [f"agent run {st['run']}   state: {state.upper() if st['alive'] else state}"]
        if st["current"]:
            c = st["current"]
            out.append(f"now: model {c['n']}/{st['total']} {c['model']} ({fmt_dur(c['elapsed_s'])})")
        if st["reason"]:
            out.append(f"reason: {st['reason']}")
        if st["heartbeat_late_s"] is not None:
            out.append(f"warning: no heartbeat for {fmt_dur(st['heartbeat_late_s'])}, but the runner process "
                       f"(PID {st['pid']}) is still there")
        out += request_lines(st)
        out += ["", "commands: bench stop | details: bench agent report --run " + st["run"]]
        return "\n".join(out)
    state = "NOT RUNNING (process gone) -> `bench resume`" if st["gone"] else st["state"]
    total, done = st["total"], st["finished_jobs"]
    bar_n = int(30 * done / total) if total else 0
    out = [f"run {st['run']}   state: {state.upper() if st['alive'] else state}",
           f"[{'#' * bar_n}{'.' * (30 - bar_n)}] {done}/{total} jobs   failed: {st['failed']}"]
    if st["remaining_s"] is not None:
        out.append(f"estimated remaining: {fmt_dur(st['remaining_s'])} (from {st['ok_jobs']} finished jobs)")
    if st["current"]:
        c = st["current"]
        out.append(f"now: #{c['n']} {c['model']} / {c['config']} - {c['phase']} ({fmt_dur(c['elapsed_s'])})")
    if st["reason"]:
        out.append(f"reason: {st['reason']}")
    if st["warning"]:
        out.append(f"warning: {st['warning']}")
    if st["heartbeat_late_s"] is not None:
        out.append(f"warning: no heartbeat for {fmt_dur(st['heartbeat_late_s'])}, but the runner process "
                   f"(PID {st['pid']}) is still there; if it stays like this, check the runner's window")
    if st["requested"]:
        r = st["requested"]
        out.append(f"requested: {r['cmd']}{' --now' if r['now'] else ' after the current job'}")
    out += request_lines(st)
    if show_jobs:
        out.append("")
        for j in st["jobs"]:
            out.append(f"{j['n']:3d} {(j['status'] or '-'):12s} {j['model']} / {j['config']}")
    elif st["last_results"]:
        out.append("")
        out.append("last results:")
        for r in st["last_results"]:
            out.append(f"  {r['model'][:34]:34s} {r['config']:12s} {r['status']:7s} "
                       f"vram+{r.get('vram_delta_mib', '-')}  decode {r.get('decode_tok_s', '-')} t/s"
                       + ("  NEAR VRAM LIMIT" if r.get("near_vram_limit") else ""))
    out.append("")
    out.append("commands: bench pause [--now] | bench resume | bench stop [--now] | bench status --jobs")
    return "\n".join(out)


def request_lines(st):
    """IF-14: the last request with its source, unless it is the run's own start."""
    r = st.get("last_request")
    if not r or (r["cmd"] == "run" and r["source"] in ("runner", None)):
        return []
    when = time.strftime("%H:%M:%S", time.localtime(r["ts"])) if r.get("ts") else "?"
    return [f"last request: {r['cmd']}{' --now' if r['now'] else ''} from {r['source'] or 'unknown'} at {when}"]


def cmd_run(a):
    if a.json:
        if a.dry_run:
            return out_json(sweep.plan_run(a.grid, a.models, a.where))
        result = sweep.start_run(a.grid, a.models, {k: getattr(a, k) for k in sweep.RUN_OPTIONS}, a.where)
        return out_json(result, result["exit_code"])
    say(sweep.stamp(f"grid: {a.grid}"))
    if a.dry_run:
        plan = sweep.plan_run(a.grid, a.models, a.where)
        for j in plan["jobs"]:
            print(f"{j['n']:3d} {j['model']} / {j['config']}")
        print(f"{len(plan['jobs'])} jobs (dry run, nothing started)")
        if plan["warning"]:
            say(sweep.stamp(f"WARNING: {plan['warning']}"))
        return 0
    return sweep.start_run(a.grid, a.models, {k: getattr(a, k) for k in sweep.RUN_OPTIONS}, a.where)["exit_code"]


def cmd_resume(a):
    result = sweep.resume_run(a.run, a.from_job, a.redo_failed, a.allow_env_change)
    if a.json:
        return out_json(result, result["exit_code"])
    if result["message"]:
        say(sweep.stamp(result["message"]))
    return result["exit_code"]


def cmd_status(a):
    if a.json:
        if a.watch:
            raise CoreError("--watch cannot be combined with --json (one JSON document per call); call status --json "
                            "repeatedly instead")
        return out_json(sweep.run_status(a.jobs))
    try:
        finished_reads = 0
        while True:
            st = sweep.run_status(a.jobs)
            if a.watch:
                os.system("cls" if os.name == "nt" else "clear")
            say(status_text(st, a.jobs))
            finished_reads = finished_reads + 1 if st["finished"] else 0
            if not a.watch or finished_reads >= 2:  # one odd reading must not end the view
                return 0
            time.sleep(3)
    except KeyboardInterrupt:
        return 0


def cmd_control(a):
    try:
        result = sweep.request_control(a.cmd, a.now)
    except CoreError as e:
        if a.json:
            return error_json(e, e.code)
        print(e)
        return e.code
    if a.json:
        return out_json(result)
    if result["kind"] == "agent":
        print(f"stop requested for agent run {result['run']}: the current attempt stops, no further model starts")
    else:
        print(f"{a.cmd} requested ({'now' if a.now else 'after the current job'})")
    return 0


def cmd_evaluate(a):
    result = sweep.evaluate_run(a.run, a.in_tokens, a.out_tokens)
    if a.json:
        return out_json(result)
    text = result["text"]
    print(text.split("\n## ", 2)[0])
    print("## " + text.split("\n## ", 2)[1])
    print(f"full report: {result['path']}")
    return 0


def cmd_check(a):
    result = check.machine_check(a.min_free_mib, a.max_util)
    code = 0 if result["ready"] else 1
    if a.json:
        return out_json(result, code)
    for f in result["findings"]:
        print(f"{f['level'].upper():5s} {f['check']:<14} {f['detail']}")
    print("ready for a run" if result["ready"] else "NOT ready for a run")
    return code


def cmd_runs(a):
    result = runs.list_runs()
    if a.json:
        return out_json(result)
    print(f"{'run':<16} {'kind':<6} {'state':<9} {'started':<20} done")
    for r in result["runs"]:
        done = f"{r['done']}/{r['total']}" if r["total"] else str(r["done"])
        unit = "jobs" if r["kind"] == "sweep" else "attempts"
        print(f"{r['run']:<16} {r['kind']:<6} {r['state']:<9} {(r['started'] or '-'):<20} {done} {unit}")
    print(f"{len(result['runs'])} run(s)")
    return 0


def cmd_close(a):
    result = runs.close_run(a.run, a.reason)
    if a.json:
        return out_json(result)
    if result["already_closed"]:
        print(f"run {a.run} was already closed")
    else:
        print(f"run {a.run} closed (was {result['closed_from']}); its files stay, it is never resumed")
    return 0


def sweep_parser():
    ap = argparse.ArgumentParser(prog="bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--grid", default=sweep.default_grid(),
                   help="grid file (default: configs/quick.local.json if present, else configs/quick.json)")
    r.add_argument("--models", help="comma separated model keys (default: the grid's list)")
    r.add_argument("--where", help=WHERE_HELP)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--repeats", type=int, default=2)
    r.add_argument("--gen-tokens", type=int, default=200)
    r.add_argument("--prompt-lines", type=int, default=60)
    r.add_argument("--load-timeout", type=int, default=240)
    r.add_argument("--gen-timeout", type=int, default=180)
    r.add_argument("--min-free-mib", type=int, default=3500)
    r.add_argument("--max-util", type=int, default=30)
    r.add_argument("--busy-retry", dest="busy_retry_s", type=int, default=sweep.BUSY_RETRY_S,
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
    c = sub.add_parser("check", help="the machine check of a run, without measuring (IF-20)")
    c.add_argument("--min-free-mib", type=int, default=3500)
    c.add_argument("--max-util", type=int, default=30)
    sub.add_parser("runs", help="every sweep and agent run with its state (IF-21)")
    x = sub.add_parser("close", help="mark an unfinished run as closed (IF-22)")
    x.add_argument("run", help="run id (see `bench runs`)")
    x.add_argument("--reason", help="why the run is closed (kept in its status)")
    add_json(sub)
    return ap


def add_json(sub):
    """IF-01: every subcommand gives a result, so every one accepts --json."""
    for parser in sub.choices.values():
        parser.add_argument("--json", action="store_true", help="print the result as one JSON document (IF-01)")


# ---------------------------------------------------------------- agent commands
def short(value, n=160):
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def describe(e):
    """One line for a trace event in `bench agent show`."""
    kind = e.get("event")
    if kind == "task_start":
        return f"task {e.get('task')} attempt {e.get('attempt')}, model {e.get('model')}, tools {e.get('tools')}"
    if kind == "prediction":
        shown = e.get("answer") or (f"[no answer; {e.get('reasoningChars')} reasoning chars] " + (e.get("text") or ""))
        return (f"round {e.get('round')}: {e.get('stopReason')}, {e.get('toolCalls')} call(s), "
                f"{e.get('duration_s')} s: {short(shown)}")
    if kind == "tool_call":
        if not e.get("parsed"):
            return f"unparsed call: {e.get('error')} raw={short(e.get('raw'), 80)}"
        extra = "" if e.get("valid", True) else f" INVALID {[p.get('code') for p in e.get('problems', [])]}"
        return f"call #{e.get('call_seq')} {e.get('name')}({short(e.get('arguments'), 100)}){extra}"
    if kind == "tool_result":
        state = "ok" if e.get("ok") else f"error {e.get('errorKind')}"
        return f"result #{e.get('call_seq')} {state}: {short(e.get('content'), 120)}"
    if kind == "limit_hit":
        return f"limit {e.get('limit')} ({e.get('value')})"
    if kind == "task_end":
        return f"status {e.get('status')}, answer: {short(e.get('answer'))}"
    return short({k: v for k, v in e.items() if k not in ("schema_version", "t", "seq", "event")})


def print_summary(model, rows, stopped):
    say("")
    say(f"{model}")
    say(f"{'task':<22} {'try':>3}  {'status':<8} {'pass':<5} {'rounds':>6} {'tools':>5}  category")
    for r in rows:
        cat = "" if r["passed"] else f"{r['primary']}" + (f"/{r['subcode']}" if r["subcode"] else "") + \
            (" (silent)" if r["silent"] else "")
        say(f"{r['task']:<22} {r['attempt']:>3}  {r['status']:<8} {'yes' if r['passed'] else 'no':<5} "
            f"{r['rounds'] or 0:>6} {r['tool_calls'] or 0:>5}  {cat}")
    passed = sum(r["passed"] for r in rows)
    say(f"passed {passed}/{len(rows)}" + (" (stopped early)" if stopped else ""))


def agent_run(a):
    if a.json:
        return out_json(agent.run_tasks(a))
    result = agent.run_tasks(a, on_model_done=print_summary)
    say(f"results: {result['results_file']}")
    say(f"report:  bench agent report --run {result['run']}")
    return 0


def agent_report(a):
    result = agent.report(a.run, a.tasks, a.k, a.reliable)
    if a.json:
        return out_json(result)
    print(result["text"].split("\n## Pass rate per task", 1)[0])
    say(f"full report: {result['path']} (and .json)")
    return 0


def agent_show(a):
    result = agent.show_attempt(a.run, a.attempt, a.model)
    if a.json:
        return out_json(result)
    row = result["row"]
    verdict = "passed" if row.get("passed") else (f"failed: {row.get('primary')}" +
                                                  (f"/{row.get('subcode')}" if row.get("subcode") else "") +
                                                  (" (silent)" if row.get("silent") else ""))
    say(f"{row.get('model')} {a.attempt}: {verdict}; rule {(row.get('evidence') or {}).get('rule')}")
    if row.get("secondary"):
        say("secondary: " + ", ".join(f"{s['category']}" + (f"/{s['subcode']}" if s.get("subcode") else "")
                                      + f" @{s.get('seq')}" for s in row["secondary"]))
    if row.get("flags"):
        say("flags: " + ", ".join(row["flags"]))
    say(f"checks: {row.get('checks')}")
    say("")
    for e in result["events"]:
        prefix = ">>" if e.get("seq") == result["mark"] else "  "
        say(f"{prefix} {e.get('seq'):>3} {e.get('event'):<12} {describe(e)}")
    say(f"\ntrace: {row['trace']}")
    return 0


def agent_parser():
    ap = argparse.ArgumentParser(prog="bench agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a task set on one or more models through the harness")
    r.add_argument("--model", help="model key from `lms ls`")
    r.add_argument("--models", help="comma separated model keys, run one after another (FA-40)")
    r.add_argument("--where", help=WHERE_HELP)
    r.add_argument("--tasks", default=str(agent.ROOT / "tasks" / "examples.json"))
    r.add_argument("--only", help="comma separated task ids")
    r.add_argument("--repeats", type=int, default=5)
    r.add_argument("--context", type=int, default=8192)
    r.add_argument("--temperature", type=float, help="overrides the temperature of the model's sampling profile")
    r.add_argument("--load-timeout", type=int, default=240)
    r.add_argument("--run-timeout", type=int, help="seconds per model for the whole task set (default: computed)")
    r.add_argument("--min-free-mib", type=int, default=3500)
    r.add_argument("--max-util", type=int, default=30)
    r.add_argument("--scripted", help="JSON file with scripted replies per task id (offline, no model)")
    p = sub.add_parser("report", help="aggregate one or more runs: pass rates, categories, chains (offline)")
    p.add_argument("--run", action="append", help="run id (repeatable; default: the latest run)")
    p.add_argument("--tasks", help="judge with this task file instead of the copy in the run folder")
    p.add_argument("--k", type=int, default=5, help="k of pass^k")
    p.add_argument("--reliable", type=float, default=0.8, help="pass rate a chain length needs to count as reliable")
    s = sub.add_parser("show", help="the steps of one attempt with the evidence of its category (offline)")
    s.add_argument("run", help="run id")
    s.add_argument("attempt", help="<task>-<number>, e.g. chain-3a-2")
    s.add_argument("--model", help="model key, when the run has several models")
    add_json(sub)
    return ap


def agent_main(argv):
    a = agent_parser().parse_args(argv)
    json_mode(a)
    try:
        return {"run": agent_run, "report": agent_report, "show": agent_show}[a.cmd](a)
    except StepError as e:
        if a.json:
            return error_json(e, 3)
        say(f"agent {a.cmd} failed: {e}")
        return 3
    except CoreError as e:
        if a.json:
            return error_json(e, e.code)
        say(f"agent {a.cmd}: {e}")
        return e.code


# ---------------------------------------------------------------- model registry commands
def size_gb(n):
    return f"{n / 1e9:.1f}" if isinstance(n, (int, float)) else "-"


def print_refresh(r):
    print(f"{r['count']} models in the registry")
    if r["first_snapshot"]:
        print("first snapshot: these models are the baseline; later downloads are marked new")
    for key in r["appeared"]:
        print(f"  new:  {key}")
    for key in r["disappeared"]:
        print(f"  gone: {key}")


def models_parser():
    ap = argparse.ArgumentParser(prog="bench models")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("refresh", help="update the registry from the installed models (`lms ls`)")
    lst = sub.add_parser("list", help="every installed model with its capability fields, own tags and the new flag")
    lst.add_argument("--where", help=WHERE_HELP)
    lst.add_argument("--new", nargs="?", type=int, const=registry.NEW_DAYS, metavar="DAYS",
                     help=f"only models first seen within DAYS days (default {registry.NEW_DAYS})")
    lst.add_argument("--refresh", action="store_true", help="update the registry first")
    add_json(sub)
    return ap


def models_main(argv):
    a = models_parser().parse_args(argv)
    json_mode(a)
    try:
        if a.cmd == "refresh":
            result = registry.refresh()
            if a.json:
                return out_json(result)
            print_refresh(result)
            return 0
        result = registry.list_models(a.where, a.new, a.refresh)
        if a.json:
            return out_json(result)
        if result["refreshed"]:
            print_refresh(result["refreshed"])
        if a.new is not None and not result["models"]:
            print(f"no models first seen within {a.new} days")
            return 0
        print(f"{'model':<44} {'params':>7} {'quant':<8} {'max ctx':>8} {'GB':>5}  tags")
        hidden = set(registry.FIELDS) | set(registry.DATES) | {"new", "key"}
        for f in result["models"]:
            key = f["key"]
            own = [k for k, v in f.items() if k not in hidden and v is True]
            flags = [n for n in ("vision", "tool_use") if f.get(n)] + own
            if f.get("new"):
                flags.append(f"new since {f['first_seen'][:10]}")
            if f.get("type") not in (None, "llm"):
                flags.insert(0, f["type"])
            print(f"{key[:44]:<44} {str(f.get('params') or '-'):>7} {str(f.get('quantization') or '-'):<8} "
                  f"{str(f.get('max_context') or '-'):>8} {size_gb(f.get('size_bytes')):>5}  {', '.join(flags)}")
        print(f"{len(result['models'])} model(s)")
        return 0
    except CoreError as e:
        if a.json:
            return error_json(e, e.code)
        print(e)
        return e.code


# ---------------------------------------------------------------- entry
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    progress.set_sink(say)
    if argv[:1] == ["agent"]:
        return agent_main(argv[1:])
    if argv[:1] == ["models"]:
        return models_main(argv[1:])
    a = sweep_parser().parse_args(argv)
    json_mode(a)
    commands = {"run": cmd_run, "resume": cmd_resume, "status": cmd_status, "evaluate": cmd_evaluate,
                "pause": cmd_control, "stop": cmd_control, "check": cmd_check, "runs": cmd_runs, "close": cmd_close}
    try:
        return commands[a.cmd](a)
    except CoreError as e:
        if a.json:
            return error_json(e, e.code)
        say(sweep.stamp(str(e)))
        return e.code
