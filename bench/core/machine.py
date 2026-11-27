"""Machine-specific settings and the environment fingerprint of results (CR-12, CR-15).

Paths come from the untracked configs/machine.local.json when it exists (see configs/machine.example.json),
otherwise from the defaults of a standard LM Studio installation on Windows. Every lookup of the fingerprint is
allowed to fail: a value that cannot be read is None, never guessed.
"""
import json
import os
import platform
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = ROOT / "configs" / "machine.local.json"
SETTING_KEYS = ("lmstudio_dir", "lms", "api_file")


def settings(path=None):
    """lmstudio_dir, lms (the lms executable) and api_file (the file with the SDK port); `configured` lists the keys
    that came from the settings file."""
    path = SETTINGS_FILE if path is None else Path(path)
    given = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    given.pop("comment", None)
    unknown = sorted(set(given) - set(SETTING_KEYS))
    if unknown:
        raise ValueError(f"{path.name}: unknown keys {unknown}; allowed: {list(SETTING_KEYS)}")
    base = Path(given.get("lmstudio_dir") or Path(os.environ.get("USERPROFILE", "")) / ".lmstudio")
    return {"lmstudio_dir": str(base),
            "lms": str(given.get("lms") or base / "bin" / "lms.exe"),
            "api_file": str(given.get("api_file") or base / "apps" / "bionic" / ".internal" / "http-server.json"),
            "configured": sorted(given)}


def lms_path():
    return settings()["lms"]


def node_env():
    """Environment for the Node helpers: LMS_API_FILE is set when the settings file names the API file or the LM
    Studio folder; otherwise the helpers use their own default (or an LMS_API_FILE the user set)."""
    s = settings()
    env = dict(os.environ)
    if {"api_file", "lmstudio_dir"} & set(s["configured"]):
        env["LMS_API_FILE"] = s["api_file"]
    return env


def _run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def selected_runtime():
    out = _run([lms_path(), "runtime", "ls"])
    if not out:
        return None
    return next((ln.split()[0] for ln in re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out).splitlines()
                 if "✓" in ln and "llama.cpp" in ln), None)


def gpu():
    """(name, total VRAM in MiB, driver version) of the first GPU, or Nones."""
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"], 15)
    if not out or not out.strip():
        return None, None, None
    name, total, driver = [x.strip() for x in out.strip().splitlines()[0].split(",")]
    return name, int(total) if total.isdigit() else None, driver


def sdk_version():
    p = ROOT / "harness" / "node_modules" / "@lmstudio" / "sdk" / "package.json"
    return json.loads(p.read_text(encoding="utf-8"))["version"] if p.is_file() else None


def harness_version():
    p = ROOT / "harness" / "agent" / "spec.ts"
    m = re.search(r'HARNESS_VERSION\s*=\s*"([^"]+)"', p.read_text(encoding="utf-8")) if p.is_file() else None
    return m.group(1) if m else None


def node_version():
    out = _run(["node", "--version"], 15)
    return out.strip().lstrip("v") if out else None


_cache = {}


def fingerprint(refresh=False):
    """The environment of this machine for result rows; read once per process. `lmstudio_app` comes from the load
    and is filled in per row."""
    if refresh or not _cache:
        name, total, driver = gpu()
        _cache.clear()
        _cache.update({"gpu": name, "vram_total_mib": total, "driver": driver, "lmstudio_app": None,
                       "runtime": selected_runtime(), "sdk": sdk_version(), "harness": harness_version(),
                       "os": platform.platform(), "python": platform.python_version(), "node": node_version()})
    return dict(_cache)
