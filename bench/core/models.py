"""Model registry (CR-20 to CR-24): the installed models with capability fields, own tags on top, the date each model
was first seen, and selection of models by capability.

  state/models.json          the registry (`bench models refresh`): the installed models with `first_seen`, and the
                             models that are gone with `gone_since`
  configs/models.local.json  own tags per model key (untracked), e.g. {"some-model": {"mtp": true}}; a tag overrides
                             a generated field of the same name

A model counts as new when it was first seen within the last days (default 7). The models of the very first snapshot
are the baseline and never count as new, because their download date is unknown.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from . import progress
from .progress import CoreError

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "state" / "models.json"
TAGS_FILE = ROOT / "configs" / "models.local.json"
SNAPSHOT_VERSION = 2
FIELDS = ("type", "vision", "tool_use", "architecture", "params", "quantization", "max_context", "size_bytes")
DATES = ("first_seen", "baseline")
NEW_DAYS = 7


def entry(m):
    """The registry fields of one `lms ls --json` record."""
    quant = m.get("quantization")
    return {"type": m.get("type"), "vision": bool(m.get("vision")), "tool_use": bool(m.get("trainedForToolUse")),
            "architecture": m.get("architecture"), "params": m.get("paramsString"),
            "quantization": quant.get("name") if isinstance(quant, dict) else quant,
            "max_context": m.get("maxContextLength"), "size_bytes": m.get("sizeBytes")}


def _now(now=None):
    return (now or datetime.now()).isoformat(timespec="seconds")


def load(snapshot=SNAPSHOT):
    """The stored registry in format 2, or None. A format 1 snapshot (two snapshots, no dates) is converted: its models
    become the baseline, first seen at the time of that snapshot."""
    if not snapshot.is_file():
        return None
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    version = data.get("schema_version")
    if version == SNAPSHOT_VERSION:
        return data
    if version == 1:  # format 1 kept the snapshot before it in models.previous.json; what was not there is new
        taken = data.get("taken")
        previous = snapshot.with_name("models.previous.json")
        before = json.loads(previous.read_text(encoding="utf-8"))["models"] if previous.is_file() else None
        return {"schema_version": SNAPSHOT_VERSION, "taken": taken, "gone": {},
                "models": {k: {**v, "first_seen": taken, "baseline": before is None or k in before}
                           for k, v in data["models"].items()}}
    raise CoreError(f"{snapshot.name}: snapshot format {version} is not known to this version of bench")


def refresh(catalog=None, snapshot=SNAPSHOT, now=None):
    """Updates the registry from `lms ls` (or the given catalog: key -> record). Returns the model count and the keys
    that appeared or disappeared with this refresh."""
    if catalog is None:
        from . import sweep
        catalog = sweep.model_catalog()
    stamp = _now(now)
    old = load(snapshot)
    first = old is None
    before = (old or {}).get("models", {})
    gone = dict((old or {}).get("gone", {}))
    models = {}
    for key, record in sorted(catalog.items()):
        dates = {k: before[key][k] for k in DATES if key in before and k in before[key]}
        if not dates:
            earlier = gone.pop(key, None)  # a model that comes back keeps its first date
            dates = ({k: earlier[k] for k in DATES if k in earlier} if earlier else
                     {"first_seen": stamp, "baseline": first})
        models[key] = {**entry(record), **dates}
    for key in set(before) - set(models):
        gone[key] = {**before[key], "gone_since": stamp}
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps({"schema_version": SNAPSHOT_VERSION, "taken": stamp, "models": models,
                                    "gone": gone}, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"count": len(models), "first_snapshot": first, "appeared": sorted(set(models) - set(before)) if old else [],
            "disappeared": sorted(set(before) - set(models))}


def tags(path=TAGS_FILE):
    given = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    given.pop("comment", None)
    for key, value in given.items():
        if not isinstance(value, dict):
            raise CoreError(f"{path.name}: the tags of '{key}' must be an object, e.g. {{\"mtp\": true}}")
    return given


def is_new(fields, days=NEW_DAYS, now=None):
    if fields.get("baseline") or not fields.get("first_seen"):
        return False
    return datetime.fromisoformat(fields["first_seen"]) >= (now or datetime.now()) - timedelta(days=days)


def registry(snapshot=SNAPSHOT, tags_file=TAGS_FILE, now=None):
    """key -> fields of the installed models with the own tags merged in (a tag wins over a generated field) and a
    computed `new` flag."""
    data = load(snapshot)
    if not data:
        raise CoreError("no model snapshot yet: run `bench models refresh`")
    own = tags(tags_file)
    return {key: {**fields, "new": is_new(fields, now=now), **own.get(key, {})} for key, fields in data["models"].items()}


def new_models(days=NEW_DAYS, snapshot=SNAPSHOT, now=None):
    """Keys of the installed models first seen within the last `days` days."""
    data = load(snapshot)
    if not data:
        raise CoreError("no model snapshot yet: run `bench models refresh`")
    return sorted(k for k, f in data["models"].items() if is_new(f, days, now))


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


def select_fresh(where, keys=None):
    """select() after a refresh, so a run chooses from the installed models; when LM Studio cannot be asked, the
    stored registry is used and a warning goes to the progress sink."""
    try:
        refresh()
    except Exception as e:  # lms missing or not answering: fall back to the stored registry
        progress.emit(f"WARNING: model registry not refreshed ({e}); using the stored snapshot")
    return select(where, keys)
