"""LIVE test of pause / resume / stop / resume on the tiny 1B model (uses the GPU for a few minutes).

Drives the `bench` command line (`python -m bench.cli`) exactly as a user would and checks after every transition that the machine
is clean: no model loaded, LM Studio config folder byte-identical to the state before the test.
"""
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench.core import sweep  # noqa: E402
from bench.core.smoke import LMS, sh  # noqa: E402

BENCH = ["-m", "bench.cli"]  # run with ROOT as the working directory
# LM Studio's per-model default-config files (internal location); the test checks that a run leaves them alone
CFG_ROOT = (Path(os.environ.get("USERPROFILE", "")) / ".lmstudio" / "apps" / "bionic" / ".internal"
            / "user-concrete-model-default-config")
MODEL = "llama-3.2-1b-instruct"
failures = []


def snapshot():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in CFG_ROOT.rglob("*") if p.is_file()}


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name, flush=True)
    if not cond:
        failures.append(name)


def cli(*args):
    p = subprocess.run([sys.executable, *BENCH, *args], capture_output=True, text=True, timeout=60, cwd=ROOT)
    return p.stdout + p.stderr


def wait_for(pred, timeout, what):
    end = time.time() + timeout
    while time.time() < end:
        st = sweep.read_json(sweep.STATUS) or {}
        if pred(st):
            return st
        time.sleep(0.5)
    check(f"timeout waiting for: {what}", False)
    return {}


def done_count(run):
    res = sweep.latest_results(ROOT / "results" / f"sweep_{run}.jsonl")
    return sum(1 for r in res.values() if r["status"] == "ok")


def clean(label, before):
    ps = sh([LMS, "ps"], 30)[1]
    check(f"{label}: no model loaded", "No models are currently loaded" in ps)
    check(f"{label}: config folder identical", snapshot() == before)


def start(*args, logname):
    f = open(ROOT / "results" / logname, "w", encoding="utf-8")
    return subprocess.Popen([sys.executable, *BENCH, *args], stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)


proc = None
before = snapshot()
try:
    proc = start("run", "--grid", str(ROOT / "configs" / "validate.json"), "--models", MODEL,
                 logname="live_control_1.log")
    st = wait_for(lambda s: s.get("state") == "running" and s.get("pid") == proc.pid
                  and str(s.get("phase", "")).startswith(("warm-up", "measuring")), 90, "first measurement")
    run = st.get("run")
    print(cli("pause", "--now").strip())
    wait_for(lambda s: s.get("state") == "paused", 90, "paused")
    check("pause --now: dropped job not recorded as done", done_count(run) == 0)
    clean("paused", before)
    check("status command shows PAUSED", "PAUSED" in cli("status"))
    time.sleep(3)
    check("still paused after 3s", (sweep.read_json(sweep.STATUS) or {}).get("state") == "paused")

    print(cli("resume").strip())
    wait_for(lambda s: s.get("state") == "running" and done_count(run) >= 1, 120, "job 1 done after resume")
    print(cli("stop").strip())  # graceful: after the current job
    proc.wait(timeout=180)
    n_stop = done_count(run)
    check("stop: process exited with code 0", proc.returncode == 0)
    check(f"stop: partial run ({n_stop} of 4 done)", 1 <= n_stop < 4)
    check("stop: state stopped", (sweep.read_json(sweep.STATUS) or {}).get("state") == "stopped")
    clean("stopped", before)

    proc = start("resume", "--from", "1", logname="live_control_2.log")
    proc.wait(timeout=400)
    check("resume --from 1: exit code 0", proc.returncode == 0)
    check("resume --from 1: all 4 done", done_count(run) == 4)
    check("final state done", (sweep.read_json(sweep.STATUS) or {}).get("state") == "done")
    clean("done", before)
    print(cli("status").strip())
finally:
    if proc and proc.poll() is None:
        sweep.send("stop", True)
        try:
            proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            print("runner did not stop; check `bench status`")
print("\nFAILURES:", failures or "none")
sys.exit(1 if failures else 0)
