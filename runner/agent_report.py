"""Report of agent runs (FA-39, FA-43, FA-44, FA-46): recomputes pass/fail and categories from the traces with the
task file copied into the run folder, then aggregates per model and task. Pure functions except load/write helpers.

  bench agent report [--run <id> ...] [--k 5] [--reliable 0.8]
"""
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import failures

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
REPORTS = ROOT / "report"
FORMAT_STUCK_SHARE = 0.8  # FA-39: this share of failures being format_invalid means the rest was not measurable


# ---------------------------------------------------------------- statistics

def wilson(k, n, z=1.96):
    """95 % Wilson score interval of k successes in n trials; (None, None) for n = 0."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def pass_hat_k(per_task, k):
    """pass^k (Yao et al. 2024): the chance that k attempts of a task all pass, C(c,k)/C(n,k), averaged over the tasks
    with at least k attempts. per_task: list of (passes, attempts)."""
    values = [math.comb(c, k) / math.comb(n, k) for c, n in per_task if n >= k]
    return sum(values) / len(values) if values else None


# ---------------------------------------------------------------- loading

def latest_run():
    files = sorted(RESULTS.glob("agent_*.jsonl"))
    if not files:
        raise SystemExit("no agent results found in results/")
    return files[-1].stem[len("agent_"):]


def load_rows(run_id):
    path = RESULTS / f"agent_{run_id}.jsonl"
    if not path.is_file():
        raise SystemExit(f"results file not found: {path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tasks_file = RESULTS / "agent" / run_id / "tasks.json"
    tasks = {}
    if tasks_file.is_file():
        tasks = {t["id"]: t for t in json.loads(tasks_file.read_text(encoding="utf-8"))["tasks"]}
    return rows, tasks


def rejudge(rows, tasks, read_events, evaluate_attempt):
    """Recomputes verdict and category of every row from its trace with the current taxonomy (FA-43)."""
    out = []
    for r in rows:
        task = tasks.get(r.get("task"))
        if task is None or not r.get("trace"):
            out.append(dict(r))  # model-level errors (task "*") and rows without a trace stay as recorded
            continue
        events = read_events(r["trace"])
        attempt = {"status": r.get("status"), "answer": r.get("answer")}
        verdict = evaluate_attempt(task, attempt, events)
        out.append({**r, **verdict, **failures.classify(task, attempt, events, verdict["passed"])})
    return out


# ---------------------------------------------------------------- aggregation

def summarize(rows, tasks, k=5, reliable=0.8):
    by_model = defaultdict(list)
    for r in rows:
        by_model[r.get("model", "?")].append(r)
    models = {}
    for model, rs in by_model.items():
        infra = [r for r in rs if r.get("primary") == "infra_error" or r.get("task") == "*"]
        scored = [r for r in rs if r not in infra]
        passed = [r for r in scored if r.get("passed")]
        failed = [r for r in scored if not r.get("passed")]
        lo, hi = wilson(len(passed), len(scored))
        per_task = defaultdict(lambda: [0, 0])
        for r in scored:
            per_task[r["task"]][1] += 1
            per_task[r["task"]][0] += 1 if r.get("passed") else 0
        categories = Counter(r.get("primary") for r in failed)
        subcodes = Counter(f"{r.get('primary')}/{r.get('subcode')}" if r.get("subcode") else r.get("primary")
                           for r in failed)
        pairs = Counter((r.get("primary"), s["category"]) for r in failed for s in r.get("secondary", []))
        flags = Counter(f for r in rs for f in r.get("flags", []))
        silent = sum(1 for r in failed if r.get("silent"))
        notes = []
        if failed and categories.get("format_invalid", 0) / len(failed) >= FORMAT_STUCK_SHARE and len(failed) >= 3:
            notes.append(f"{categories['format_invalid']} of {len(failed)} failures are format_invalid: the model's "
                         "tool calls were not recognized, so its other abilities could not be measured (FA-39).")
        if infra:
            notes.append(f"{len(infra)} attempt(s) excluded as infra_error.")
        models[model] = {
            "attempts": len(scored), "passed": len(passed), "pass_rate": len(passed) / len(scored) if scored else None,
            "wilson95": [lo, hi], "pass_hat_k": pass_hat_k(list(per_task.values()), k), "k": k,
            "failed": len(failed), "silent": silent, "silent_share_of_attempts": silent / len(scored) if scored else None,
            "infra": len(infra),
            "median_rounds": statistics.median([r.get("rounds") or 0 for r in scored]) if scored else None,
            "median_seconds": statistics.median([r.get("seconds") or 0 for r in scored]) if scored else None,
            "per_task": {t: {"passed": c, "attempts": n} for t, (c, n) in sorted(per_task.items())},
            "categories": dict(categories), "subcodes": dict(subcodes),
            "pairs": {f"{a} -> {b}": n for (a, b), n in pairs.most_common()}, "flags": dict(flags),
            "longest_reliable_chain": longest_chain(per_task, tasks, reliable),
            "notes": notes,
            "mitigations": {c: failures.MITIGATIONS[c] for c, _ in categories.most_common(3) if c in failures.MITIGATIONS},
            "failures": [{"task": r["task"], "attempt": r.get("attempt"), "category": r.get("primary"),
                          "subcode": r.get("subcode"), "silent": r.get("silent"),
                          "seq": (r.get("evidence") or {}).get("seq"), "rule": (r.get("evidence") or {}).get("rule")}
                         for r in failed],
        }
    return models


def longest_chain(per_task, tasks, reliable):
    """FA-44: per chain length the pooled pass rate; a length counts when its rate is at least `reliable` and every
    shorter length counts too. Returns the length (0 if even length 1 fails) and the per-length numbers."""
    pooled = defaultdict(lambda: [0, 0])
    for tid, (c, n) in per_task.items():
        length = tasks.get(tid, {}).get("chain_length")
        if length:
            pooled[length][0] += c
            pooled[length][1] += n
    lengths = {}
    best = 0
    still = True
    for length in sorted(pooled):
        c, n = pooled[length]
        ok = n > 0 and c / n >= reliable
        lo, hi = wilson(c, n)
        lengths[length] = {"passed": c, "attempts": n, "rate": c / n if n else None, "wilson95": [lo, hi],
                           "reliable": ok}
        if still and ok:
            best = length
        else:
            still = False
    return {"length": best, "threshold": reliable, "per_length": lengths}


# ---------------------------------------------------------------- Markdown

def pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def ci(pair):
    lo, hi = pair
    return "n/a" if lo is None else f"{100 * lo:.0f}–{100 * hi:.0f}%"


def markdown(run_ids, models, meta):
    names = sorted(models)
    task_ids = sorted({t for m in models.values() for t in m["per_task"]})
    cats = [c for c in failures.CATEGORIES if any(models[m]["categories"].get(c) for m in names)]
    lines = [f"# Agent report: {', '.join(run_ids)}", "",
             f"Taxonomy version {failures.TAXONOMY_VERSION}; task file hash {meta.get('tasks_hash', 'n/a')}"
             + (f" (re-judged with {meta['rejudged_with']})" if meta.get("rejudged_with") else "") + "; "
             "categories recomputed from the traces. Wilson intervals are 95 %. Mitigations are possible mitigations, "
             "**not measured**.", "", "## Summary", "",
             "| Model | Attempts | Passed | Rate (95 % CI) | pass^k | Silent failures | Median rounds | Median s | "
             "Longest reliable chain | Infra excluded |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for m in names:
        s = models[m]
        chain = s["longest_reliable_chain"]
        phk = "n/a" if s["pass_hat_k"] is None else f"{s['pass_hat_k']:.2f}"
        lines.append(f"| {m} | {s['attempts']} | {s['passed']} | {pct(s['pass_rate'])} ({ci(s['wilson95'])}) | "
                     f"{phk} (k={s['k']}) | "
                     f"{s['silent']} ({pct(s['silent_share_of_attempts'])} of attempts) | {s['median_rounds']} | "
                     f"{s['median_seconds']:.1f} | {chain['length']} | {s['infra']} |")
    notes = [(m, n) for m in names for n in models[m]["notes"]]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {m}: {n}" for m, n in notes]
    lines += ["", "## Pass rate per task", "", "| Task | " + " | ".join(names) + " |",
              "|---|" + "---|" * len(names)]
    for t in task_ids:
        cells = []
        for m in names:
            v = models[m]["per_task"].get(t)
            cells.append(f"{v['passed']}/{v['attempts']}" if v else "–")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lengths = sorted({n for m in names for n in models[m]["longest_reliable_chain"]["per_length"]})
    lines += ["", "## Chain length (✓ = reliable)", "", "| Model | " + " | ".join(str(n) for n in lengths) + " |",
              "|---|" + "---|" * len(lengths)]
    for m in names:
        per = models[m]["longest_reliable_chain"]["per_length"]
        lines.append(f"| {m} | " + " | ".join(
            f"{per[n]['passed']}/{per[n]['attempts']}{' ✓' if per[n]['reliable'] else ''}" if n in per else "–"
            for n in lengths) + " |")
    lines += ["", "## Failure categories (primary)", "", "| Category | " + " | ".join(names) + " |",
              "|---|" + "---|" * len(names)]
    for c in cats:
        lines.append(f"| `{c}` | " + " | ".join(str(models[m]["categories"].get(c, 0)) for m in names) + " |")
    lines += ["", "## Subcodes", "", "| Model | Category / subcode | Count |", "|---|---|---|"]
    for m in names:
        for sc, n in sorted(models[m]["subcodes"].items(), key=lambda x: -x[1]):
            lines.append(f"| {m} | `{sc}` | {n} |")
    lines += ["", "## Primary → secondary categories", "", "| Model | Pair | Count |", "|---|---|---|"]
    for m in names:
        for pair, n in models[m]["pairs"].items():
            lines.append(f"| {m} | {pair} | {n} |")
    lines += ["", "## Flags", "", "| Flag | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for f in failures.FLAGS:
        lines.append(f"| `{f}` | " + " | ".join(str(models[m]["flags"].get(f, 0)) for m in names) + " |")
    lines += ["", "## Possible mitigations (not measured)", ""]
    for m in names:
        for c, text in models[m]["mitigations"].items():
            lines.append(f"- {m}, `{c}`: {text}")
    lines += ["", "## Failed attempts (evidence)", "",
              "| Model | Task | Attempt | Category | Silent | Trace event | Rule |", "|---|---|---|---|---|---|---|"]
    for m in names:
        for f in models[m]["failures"]:
            cat = f["category"] + (f"/{f['subcode']}" if f["subcode"] else "")
            lines.append(f"| {m} | {f['task']} | {f['attempt']} | `{cat}` | {'yes' if f['silent'] else 'no'} | "
                         f"{f['seq']} | {f['rule']} |")
    return "\n".join(lines) + "\n"


def write(run_ids, models, meta):
    REPORTS.mkdir(exist_ok=True)
    stem = "agent_" + "+".join(run_ids)
    md = REPORTS / f"{stem}.md"
    md.write_text(markdown(run_ids, models, meta), encoding="utf-8")
    (REPORTS / f"{stem}.json").write_text(json.dumps({"runs": run_ids, "taxonomy_version": failures.TAXONOMY_VERSION,
                                                      **meta, "models": models}, indent=1), encoding="utf-8")
    return md
