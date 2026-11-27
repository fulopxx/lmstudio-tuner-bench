"""Every run at a glance (`bench runs`, IF-21) and closing an unfinished run (`bench close`, IF-22).

Runs come from the state folders (state/runs/<id>/) and from the result files (results/sweep_<id>.jsonl,
results/agent_<id>.jsonl), so runs written before per-run state are listed too. A run without a status file is `done`
when every job of its plan has a result, otherwise `unknown`; a run whose status is active but whose process is gone
is `gone`.

`closed` (agreed 2026-11-27): a stopped, aborted, gone or unknown run can be closed. Its files stay, it stays readable
and can be evaluated, but it is never resumed. A finished (`done`) or living run cannot be closed.
"""
import time
from datetime import datetime

from . import results, runstate, sweep
from .progress import CoreError

CLOSABLE = ("stopped", "aborted", "gone", "unknown")


def _started(run_id):
    try:
        return datetime.strptime(run_id, "%Y%m%d_%H%M%S").isoformat(timespec="seconds")
    except ValueError:
        return None


def _ids():
    """run id -> kind as far as the file names tell (None when only a state folder exists)."""
    ids = {}
    runs_dir = runstate.STATE / "runs"
    if runs_dir.is_dir():
        for d in runs_dir.iterdir():
            if d.is_dir():
                ids[d.name] = None
    for kind in ("sweep", "agent"):
        for path in (sweep.ROOT / "results").glob(f"{kind}_*.jsonl"):
            ids[path.stem[len(kind) + 1:]] = kind
    return ids


def describe(run_id, kind_hint=None):
    """One run: id, kind, state, start time, finished jobs (sweep) or judged attempts (agent)."""
    st = runstate.read_status(run_id)
    plan = runstate.read_json(runstate.run_dir(run_id) / "plan.json")
    kind = (st or {}).get("kind") or kind_hint or ("sweep" if plan else "agent")
    item = {"run": run_id, "kind": kind, "state": None, "alive": False, "started": _started(run_id),
            "done": 0, "total": None, "closed_from": (st or {}).get("closed_from")}
    if kind == "sweep":
        path = sweep.ROOT / "results" / f"sweep_{run_id}.jsonl"
        rows = list(results.read_rows(path)) if path.exists() else []
        if plan and all("job_id" in r for r in rows):
            have = {r["job_id"]: r for r in rows}
            item["done"] = sum(1 for j in plan["jobs"] if j["id"] in have and have[j["id"]]["status"] != "invalidated")
            item["total"] = len(plan["jobs"]) or None
        else:  # the earliest sweeps wrote rows without job ids and kept no plan
            item["done"] = sum(1 for r in rows if r.get("status") == "ok")
    else:
        path = sweep.ROOT / "results" / f"agent_{run_id}.jsonl"
        item["done"] = sum(1 for r in results.read_rows(path) if r.get("task") != "*") if path.exists() else 0
    if st:
        item["alive"] = runstate.runner_alive(st)
        item["state"] = "gone" if st.get("state") in runstate.ACTIVE_STATES and not item["alive"] else st.get("state")
    elif item["total"] and item["done"] == item["total"]:
        item["state"] = "done"
    else:
        item["state"] = "unknown"
    return item


def list_runs():
    """Every sweep and agent run, oldest first."""
    return {"runs": [describe(run_id, kind) for run_id, kind in sorted(_ids().items())]}


def close_run(run_id, reason=None):
    """Marks an unfinished run as closed (IF-22). Nothing is deleted; only the run's status file is written."""
    known = _ids()
    if run_id not in known:
        raise CoreError(f"no run {run_id}; see `bench runs`")
    item = describe(run_id, known[run_id])
    lock = runstate.active()
    if item["alive"] or (lock and lock.get("run") == run_id):
        raise CoreError(f"run {run_id} is active; stop it first (`bench stop`)")
    if item["state"] == "closed":
        return {"run": run_id, "state": "closed", "already_closed": True, "closed_from": item["closed_from"]}
    if item["state"] not in CLOSABLE:
        raise CoreError(f"run {run_id} is {item['state']}; only an unfinished run ({', '.join(CLOSABLE)}) can be "
                        "closed")
    st = runstate.read_status(run_id) or {}
    runstate.write_json(runstate.status_path(run_id), {
        **st, "run": run_id, "kind": item["kind"], "state": "closed", "phase": "closed", "closed_at": time.time(),
        "closed_from": item["state"], "reason": reason or "closed by the user"})
    return {"run": run_id, "state": "closed", "already_closed": False, "closed_from": item["state"]}
