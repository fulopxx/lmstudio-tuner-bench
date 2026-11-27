"""Result rows: the common envelope, reading with migration of older rows, and the version check (CR-10 to CR-14).

A row of format version 1 starts with `schema_version` (the result format, independent of the task file version),
`kind` (`sweep` or `agent`), `run` and `env` (the fingerprint of bench.core.machine). Rows written before the
envelope have no `kind`; they are converted in memory when read, the file itself is never rewritten.
"""
import json
from pathlib import Path

from .progress import CoreError

SCHEMA_VERSION = 1
KINDS = ("sweep", "agent")
ENV_KEYS = ("gpu", "vram_total_mib", "driver", "lmstudio_app", "runtime", "sdk", "harness", "os", "python", "node")


def envelope(kind, run, row, env):
    """A new row in the current format; `lmstudio_app` of the env is taken from the row's load result."""
    if kind not in KINDS:
        raise ValueError(f"unknown result kind {kind!r}")
    body = {k: v for k, v in row.items() if k not in ("schema_version", "kind", "run", "env")}
    full_env = {k: env.get(k) for k in ENV_KEYS}
    full_env["lmstudio_app"] = row.get("app_version") or env.get("lmstudio_app")
    return {"schema_version": SCHEMA_VERSION, "kind": kind, "run": run, **body, "env": full_env}


def migrate(row, source="row"):
    """A row of any known format in the current format. Raises CoreError for a newer format."""
    if "kind" in row:
        version = row.get("schema_version")
        if not isinstance(version, int) or version > SCHEMA_VERSION:
            raise CoreError(f"{source}: result format version {version} is newer than this version of bench "
                            f"knows ({SCHEMA_VERSION}); update bench to read it")
        return row
    # format 0: written before the envelope; agent rows carried the task file version as schema_version
    new = dict(row)
    kind = "agent" if "task" in row or "attempt" in row else "sweep"
    if kind == "agent" and "schema_version" in new:
        new["tasks_schema_version"] = new.pop("schema_version")
    old_env = row.get("env") if isinstance(row.get("env"), dict) else {}
    env = {k: old_env.get(k) for k in ENV_KEYS}
    for key, old in (("runtime", "runtime"), ("driver", "driver"), ("sdk", "loader")):
        value = old_env.get(old) if old in old_env else row.get(old)
        if key == "sdk" and isinstance(value, str) and value.startswith("@lmstudio/sdk "):
            value = value[len("@lmstudio/sdk "):]
        env[key] = value if value not in ("?", "") else None
    env["lmstudio_app"] = row.get("app_version")
    new.pop("env", None)
    return {"schema_version": SCHEMA_VERSION, "kind": kind, "run": row.get("run"), **new, "env": env,
            "migrated_from": 0}


def read_rows(path):
    """Every row of a result file in the current format."""
    path = Path(path)
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            rows.append(migrate(json.loads(line), f"{path.name}:{n}"))
    return rows
