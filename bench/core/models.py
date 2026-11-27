"""Model registry (CR-20 to CR-24): a snapshot of the installed models with capability fields, own tags on top, the
models that are new since the previous snapshot, and selection of models by capability.

  state/models.json            the latest snapshot (`bench models refresh`)
  state/models.previous.json   the snapshot before it; the difference gives the new downloads
  configs/models.local.json    own tags per model key (untracked), e.g. {"some-model": {"mtp": true}}; a tag overrides
                               a generated field of the same name
"""
import json
from datetime import datetime
from pathlib import Path

from .progress import CoreError

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "state" / "models.json"
PREVIOUS = ROOT / "state" / "models.previous.json"
TAGS_FILE = ROOT / "configs" / "models.local.json"
SNAPSHOT_VERSION = 1
FIELDS = ("type", "vision", "tool_use", "architecture", "params", "quantization", "max_context", "size_bytes")


def entry(m):
    """The registry fields of one `lms ls --json` record."""
    quant = m.get("quantization")
    return {"type": m.get("type"), "vision": bool(m.get("vision")), "tool_use": bool(m.get("trainedForToolUse")),
            "architecture": m.get("architecture"), "params": m.get("paramsString"),
            "quantization": quant.get("name") if isinstance(quant, dict) else quant,
            "max_context": m.get("maxContextLength"), "size_bytes": m.get("sizeBytes")}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def refresh(catalog=None, snapshot=SNAPSHOT, previous=PREVIOUS):
    """Writes a new snapshot from `lms ls` (or the given catalog: key -> record); the old one becomes the previous
    snapshot. Returns the model count and the keys that are new or gone since then."""
    if catalog is None:
        from . import sweep
        catalog = sweep.model_catalog()
    models = {key: entry(m) for key, m in sorted(catalog.items())}
    old = _read(snapshot)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if old:
        previous.write_text(json.dumps(old, indent=1, ensure_ascii=False), encoding="utf-8")
    snapshot.write_text(json.dumps({"schema_version": SNAPSHOT_VERSION, "taken": datetime.now().isoformat(
        timespec="seconds"), "models": models}, indent=1, ensure_ascii=False), encoding="utf-8")
    before = set((old or {}).get("models", {}))
    return {"count": len(models), "new": sorted(set(models) - before) if old else [],
            "gone": sorted(before - set(models)), "first_snapshot": old is None}


def tags(path=TAGS_FILE):
    given = _read(path) or {}
    given.pop("comment", None)
    for key, value in given.items():
        if not isinstance(value, dict):
            raise CoreError(f"{path.name}: the tags of '{key}' must be an object, e.g. {{\"mtp\": true}}")
    return given


def registry(snapshot=SNAPSHOT, tags_file=TAGS_FILE):
    """key -> fields of the latest snapshot with the own tags merged in (a tag wins over a generated field)."""
    data = _read(snapshot)
    if not data:
        raise CoreError("no model snapshot yet: run `bench models refresh`")
    own = tags(tags_file)
    return {key: {**fields, **own.get(key, {})} for key, fields in data["models"].items()}


def new_models(snapshot=SNAPSHOT, previous=PREVIOUS):
    """Keys present in the latest snapshot and missing from the previous one."""
    now, before = _read(snapshot), _read(previous)
    if not now:
        raise CoreError("no model snapshot yet: run `bench models refresh`")
    if not before:
        return []
    return sorted(set(now["models"]) - set(before["models"]))


def matches(fields, term):
    """One filter term: `name` (true), `!name` (false or missing) or `name=value` (case-insensitive)."""
    if "=" in term:
        name, value = term.split("=", 1)
        return str(fields.get(name.strip())).lower() == value.strip().lower()
    if term.startswith("!"):
        return not fields.get(term[1:].strip())
    return bool(fields.get(term.strip()))


def select(where, keys=None, reg=None):
    """Model keys whose fields match every comma-separated term of `where`, in the order of `keys` (or sorted).
    An empty selection is an error (CR-24)."""
    reg = registry() if reg is None else reg
    terms = [t for t in (where or "").split(",") if t.strip()]
    if not terms:
        raise CoreError("empty capability filter")
    unknown = [k for k in (keys or []) if k not in reg]
    if unknown:
        raise CoreError(f"not in the model snapshot: {unknown}; run `bench models refresh`")
    chosen = [k for k in (keys or sorted(reg)) if all(matches(reg[k], t) for t in terms)]
    if not chosen:
        raise CoreError(f"no model matches the filter '{where}'")
    return chosen
