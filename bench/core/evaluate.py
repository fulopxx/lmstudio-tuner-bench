"""Evaluate a sweep: estimated response time per configuration, recommendations and warnings.

Ranking metric: estimated seconds for one request = in_tokens / prompt speed + out_tokens / decode speed.
It combines the two speeds according to how the model is used (long input vs long output).

Warnings are heuristics, not measurements:
  spill?    prompt speed below half of the model's best, or (full GPU offload) decode below 60% of the
            model's best: typical when VRAM spills into shared system memory
  unstable  the repeated runs differ by more than 10% (decode) or 25% (prompt)
"""
import statistics

from . import results

PROMPT_SPILL, DECODE_SPILL = 0.5, 0.6
DECODE_SPREAD, PROMPT_SPREAD = 0.10, 0.25


def load_rows(path):
    rows = {}
    for r in results.read_rows(path):
        rows[r["job_id"]] = r
    return [r for r in rows.values() if r["status"] != "invalidated"]


def spread(values):
    values = [v for v in values if v]
    return (max(values) - min(values)) / statistics.median(values) if len(values) > 1 else 0.0


def analyze(rows, in_tokens=2000, out_tokens=500):
    """Returns {model: [entry, ...]} in sweep order; each entry has 'est_s' and 'flags'."""
    models = {}
    for r in rows:
        models.setdefault(r["model"], []).append(r)
    result = {}
    for model, mrows in models.items():
        ok = [r for r in mrows if r["status"] == "ok" and r.get("prompt_tok_s") and r.get("decode_tok_s")]
        best_prompt = max((r["prompt_tok_s"] for r in ok), default=0)
        best_decode = max((r["decode_tok_s"] for r in ok), default=0)
        entries = []
        for r in mrows:
            s = r.get("settings", {})
            e = {"config": r["config"], "status": r["status"], "ctx": s.get("context_length"),
                 "kv": s.get("kv_quant") or "f16", "offload": s.get("offload_ratio"),
                 "batch": s.get("eval_batch_size"), "flash": s.get("flash_attention"),
                 "prompt": r.get("prompt_tok_s"), "decode": r.get("decode_tok_s"),
                 "vram_peak": r.get("vram_peak_mib"), "est_s": None, "flags": []}
            if r in ok:
                e["est_s"] = round(in_tokens / r["prompt_tok_s"] + out_tokens / r["decode_tok_s"], 1)
                if (r["prompt_tok_s"] < PROMPT_SPILL * best_prompt
                        or (s.get("offload_ratio") == 1 and r["decode_tok_s"] < DECODE_SPILL * best_decode)):
                    e["flags"].append("spill?")
                runs = r.get("runs", [])
                if (spread([x.get("decode_tok_s") for x in runs]) > DECODE_SPREAD
                        or spread([x.get("prompt_tok_s") for x in runs]) > PROMPT_SPREAD):
                    e["flags"].append("unstable")
            entries.append(e)
        result[model] = entries
    return result


def recommendations(analysis):
    """Per model and context length: the fastest configuration by measured estimate. If that one carries a
    flag, the fastest unflagged configuration is listed as an alternative (flags warn, they do not rank)."""
    recs = []
    for model, entries in analysis.items():
        by_ctx = {}
        for e in entries:
            if e["est_s"] is not None:
                by_ctx.setdefault(e["ctx"], []).append(e)
        for ctx in sorted(by_ctx):
            best = min(by_ctx[ctx], key=lambda e: e["est_s"])
            clean = [e for e in by_ctx[ctx] if not e["flags"]]
            alt = min(clean, key=lambda e: e["est_s"]) if best["flags"] and clean else None
            recs.append({"model": model, "ctx": ctx, "candidates": len(by_ctx[ctx]),
                         "alternative": f"{alt['config']} ({alt['est_s']} s)" if alt else "",
                         **{k: best[k] for k in
                            ("config", "kv", "offload", "batch", "prompt", "decode", "est_s", "flags")}})
    return recs


def report(rows, run_id, in_tokens, out_tokens):
    analysis = analyze(rows, in_tokens, out_tokens)
    out = [f"# Evaluation of sweep {run_id}", "",
           f"Ranking: estimated seconds for {in_tokens} input + {out_tokens} output tokens. Flags are heuristics.", ""]
    before = [r["vram_before_mib"] for r in rows if r.get("vram_before_mib") is not None]
    if before and max(before) - min(before) > 500:
        out += [f"**Warning:** GPU memory used by other programs varied between {min(before)} and {max(before)} MiB "
                "during this run; compare configurations with caution.", ""]
    failed = [r for r in rows if r["status"] != "ok"]
    if failed:
        out += [f"**{len(failed)} failed job(s):** " + ", ".join(r["job_id"] for r in failed), ""]
    out += ["## Recommendations", "",
            "| model | context | config | KV | offload | batch | prompt t/s | decode t/s | est. s | choices | flags "
            "| unflagged alternative |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in recommendations(analysis):
        out.append(f"| {x['model']} | {x['ctx']} | {x['config']} | {x['kv']} | {x['offload']} | {x['batch']} | "
                   f"{x['prompt']} | {x['decode']} | {x['est_s']} | {x['candidates']} | {' '.join(x['flags'])} | "
                   f"{x['alternative']} |")
    for model, entries in analysis.items():
        out += ["", f"## {model}", "",
                "| config | context | prompt t/s | decode t/s | est. s | VRAM peak MiB | flags |",
                "|---|---|---|---|---|---|---|"]
        for e in sorted(entries, key=lambda e: (e["est_s"] is None, e["est_s"] or 0)):
            out.append(f"| {e['config']} | {e['ctx']} | {e['prompt']} | {e['decode']} | "
                       f"{e['est_s'] if e['est_s'] is not None else e['status']} | {e['vram_peak']} | "
                       f"{' '.join(e['flags'])} |")
    return "\n".join(out) + "\n"
