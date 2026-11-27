"""`bench check` (IF-20): the machine check of a run without measuring and without changing anything.

Every finding is {"check", "level", "value", "detail"} with level `ok`, `warn` (a run can still start: it handles this
itself, e.g. unloads its own model left over from a killed run) or `fail` (a run would pause or stop). assess() is the
shared rule set: the sweep runner and the agent run use it too, after removing their own left-over model.
"""
import json
import statistics
import time

from . import runstate
from .smoke import LMS, StepError, sh

OWN_IDENTIFIERS = ("bench-sweep", "bench-agent")  # the model instances that bench runs load and remove
NO_MODELS = "No models are currently loaded"


def finding(check, level, value, detail):
    return {"check": check, "level": level, "value": value, "detail": detail}


def loaded_from_text(ps_text):
    """The loaded instances as far as the text of `lms ps` tells: [] for none, otherwise a list naming the own
    identifiers it contains and "?" for anything else it may list."""
    if NO_MODELS in ps_text:
        return []
    return [i for i in OWN_IDENTIFIERS if i in ps_text] or ["?"]


def assess(loaded, samples, min_free_mib, max_util, leftover_ok=True):
    """Findings on the loaded model instances (identifiers) and the GPU (samples of [used MiB, total MiB, util %]).
    A runner passes leftover_ok=False after it has tried to unload its own left-over model: then any loaded model
    fails, as before."""
    out = []
    foreign = [i for i in loaded if i not in OWN_IDENTIFIERS]
    if not loaded:
        out.append(finding("loaded_models", "ok", [], "no model loaded"))
    elif foreign or not leftover_ok:
        out.append(finding("loaded_models", "fail", loaded,
                           "a model is loaded that this run did not load; unload it in LM Studio"))
    else:
        out.append(finding("loaded_models", "warn", loaded,
                           f"'{loaded[0]}' left over from an earlier run; the next run unloads it"))
    used, total = samples[-1][0], samples[-1][1]
    free = total - used
    out.append(finding("free_vram_mib", "ok" if free >= min_free_mib else "fail", free,
                       f"{free} MiB VRAM free (needs {min_free_mib})" if free >= min_free_mib else
                       f"only {free} MiB VRAM free (< {min_free_mib}): game or GPU app running?"))
    util = statistics.median(s[2] for s in samples)
    out.append(finding("gpu_util_pct", "ok" if util <= max_util else "fail", util,
                       f"GPU {util}% busy (median of {len(samples)} samples, limit {max_util}%)" if util <= max_util
                       else f"GPU {util}% busy (> {max_util}%): close GPU-heavy apps"))
    return out


def first_failure(findings):
    return next((f for f in findings if f["level"] == "fail"), None)


def loaded_instances():
    """Identifiers of the loaded model instances (`lms ps --json`); falls back to the text output."""
    rc, out = sh([LMS, "ps", "--json"], 30)
    try:
        return [m.get("identifier") or m.get("modelKey") or "?" for m in json.loads(out[out.index("["):])]
    except ValueError:
        rc, out = sh([LMS, "ps"], 30)
        if rc != 0:
            raise StepError("fail", "lms ps failed")
        return loaded_from_text(out)


def machine_check(min_free_mib=3500, max_util=30, samples=3):
    """Runs every check of a run once, read only. Returns `ready` (no failure) and the findings."""
    from . import agent, sweep  # late: both import this module
    out = []
    try:
        loaded = loaded_instances()
        out.append(finding("lms", "ok", None, "lms answers"))
    except (StepError, OSError) as e:
        out.append(finding("lms", "fail", None, f"lms not usable: {e}"))
        loaded = None
    gpu = []
    try:
        for i in range(samples):
            gpu.append(sweep.gpu_state())
            if i < samples - 1:
                time.sleep(0.7)
    except (StepError, OSError, ValueError, IndexError) as e:
        out.append(finding("gpu", "fail", None, f"nvidia-smi not usable: {e}"))
        gpu = []
    if loaded is not None and gpu:
        out += assess(loaded, gpu, min_free_mib, max_util)
    try:
        runtime = sweep.environment()["runtime"]
        warning = sweep.runtime_warning(runtime, [{"settings": {"offload_ratio": 1}}])
        out.append(finding("runtime", "warn" if warning else "ok", runtime,
                           warning or "the selected GGUF runtime has GPU support"))
    except (StepError, OSError) as e:
        out.append(finding("runtime", "warn", None, f"runtime not read: {e}"))
    problem = agent.harness_problem()
    out.append(finding("harness", "fail" if problem else "ok", None,
                       problem or "Node.js and the harness packages are there (every load needs them)"))
    lock = runstate.active()
    out.append(finding("active_run", "fail" if lock else "ok", lock and lock["run"],
                       f"{lock['kind']} run {lock['run']} is active" if lock else "no run is active"))
    return {"ready": first_failure(out) is None, "min_free_mib": min_free_mib, "max_util": max_util, "findings": out}
