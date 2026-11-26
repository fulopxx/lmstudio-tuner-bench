"""Temporary edits of LM Studio per-model default-config files, with guaranteed restore.

Why: KV-cache quantization, CPU threads and GPU offload ratio cannot be set through the REST load call;
LM Studio reads them from the per-model default-config JSON.

Safety:
  * Before the first write of a file its original bytes (or "did not exist") are recorded in a journal
    (backups/active.json) and copied to backups/<run_id>/.
  * restore_all() puts every file back byte for byte (deletes files that did not exist before) and
    verifies the result. Call it in `finally`.
  * If a run is killed, the journal survives; recover() at the next start restores first.
"""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG_ROOT = (Path(os.environ.get("USERPROFILE", "")) / ".lmstudio" / "apps" / "bionic" / ".internal"
            / "user-concrete-model-default-config")
BACKUP_ROOT = ROOT / "backups"
JOURNAL = BACKUP_ROOT / "active.json"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".bench-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def config_path(model_path):
    """model_path as printed by `lms ls --json`, e.g. publisher/repo/file.gguf"""
    if not CFG_ROOT.is_dir():
        raise RuntimeError(f"LM Studio default-config folder not found: {CFG_ROOT}")
    p = (CFG_ROOT / (model_path + ".json")).resolve()
    if CFG_ROOT.resolve() not in p.parents:
        raise RuntimeError(f"refusing path outside the config folder: {model_path}")
    return p


def fields_from_settings(s):
    q = s.get("kv_quant")
    quant = {"checked": bool(q), "value": q or "q8_0"}
    return {
        "llm.load.llama.autoFit": False,
        "llm.load.contextLength": s["context_length"],
        "llm.load.llama.acceleration.offloadRatio": s["offload_ratio"],
        "llm.load.llama.flashAttention": s["flash_attention"],
        "llm.load.llama.physicalBatchSize": s["physical_batch_size"],
        "llm.load.llama.cpuThreadPoolSize": s["threads"],
        "llm.load.useUnifiedKvCache": s["unified_kv"],
        "llm.load.llama.kCacheQuantizationType": quant,
        "llm.load.llama.vCacheQuantizationType": dict(quant),
    }


class ConfigStore:
    def __init__(self, run_id):
        self.run_id = run_id

    @staticmethod
    def _load_journal():
        return json.loads(JOURNAL.read_text(encoding="utf-8")) if JOURNAL.exists() else {}

    @staticmethod
    def _save_journal(j):
        _atomic_write(JOURNAL, json.dumps(j, indent=1).encode("utf-8"))

    def apply(self, model_path, settings):
        p = config_path(model_path)
        j = self._load_journal()
        key = str(p)
        if key not in j:  # record the ORIGINAL state exactly once, before any write
            entry = {"existed": p.exists(), "backup": None, "sha256": None}
            if p.exists():
                data = p.read_bytes()
                b = BACKUP_ROOT / self.run_id / f"{len(j):03d}_{p.name}"
                _atomic_write(b, data)
                entry.update({"backup": str(b), "sha256": _sha(data)})
            j[key] = entry
            self._save_journal(j)
        entry = j[key]
        if entry["existed"]:
            doc = json.loads(Path(entry["backup"]).read_text(encoding="utf-8"))
        else:
            doc = {"preset": "", "operation": {"fields": []}, "load": {"fields": []}}
        fields = {f["key"]: f["value"] for f in doc.setdefault("load", {}).setdefault("fields", [])}
        fields.update(fields_from_settings(settings))
        doc["load"]["fields"] = [{"key": k, "value": v} for k, v in fields.items()]
        _atomic_write(p, json.dumps(doc, indent=2).encode("utf-8"))

    @classmethod
    def restore_all(cls):
        """Restore every journaled file. Returns (restored_list, problems_list)."""
        j = cls._load_journal()
        done, problems = [], []
        for key, e in list(j.items()):
            p = Path(key)
            try:
                if e["existed"]:
                    data = Path(e["backup"]).read_bytes()
                    if _sha(data) != e["sha256"]:
                        raise RuntimeError("backup checksum mismatch")
                    _atomic_write(p, data)
                    if _sha(p.read_bytes()) != e["sha256"]:
                        raise RuntimeError("verification after restore failed")
                else:
                    if p.exists():
                        p.unlink()  # we created it
                done.append(key)
                del j[key]
            except Exception as ex:
                problems.append(f"{key}: {ex!r}")
        if j:
            cls._save_journal(j)
        elif JOURNAL.exists():
            JOURNAL.unlink()
        return done, problems
