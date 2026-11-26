"""Offline test of backup/restore (temp directories only, never touches the real LM Studio folder)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runner"))
import config_store as cs  # noqa: E402

SETTINGS = {"context_length": 4096, "offload_ratio": 0.5, "flash_attention": True,
            "physical_batch_size": 256, "threads": 4, "unified_kv": True, "kv_quant": "q8_0"}


class ConfigStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self._old = (cs.CFG_ROOT, cs.BACKUP_ROOT, cs.JOURNAL)
        cs.CFG_ROOT, cs.BACKUP_ROOT = t / "cfg", t / "backups"
        cs.JOURNAL = cs.BACKUP_ROOT / "active.json"
        cs.CFG_ROOT.mkdir()
        self.existing = cs.CFG_ROOT / "pub" / "repo" / "a.gguf.json"
        self.existing.parent.mkdir(parents=True)
        self.original = (b'{"preset":"","operation":{"fields":[]},"load":{"fields":['
                         b'{"key":"llm.load.contextLength","value":111},'
                         b'{"key":"user.custom","value":7}]}}\r\n')
        self.existing.write_bytes(self.original)
        self.absent = cs.CFG_ROOT / "pub" / "repo" / "b.gguf.json"

    def tearDown(self):
        cs.CFG_ROOT, cs.BACKUP_ROOT, cs.JOURNAL = self._old
        self.tmp.cleanup()

    def fields(self, p):
        return {f["key"]: f["value"] for f in json.loads(p.read_text())["load"]["fields"]}

    def test_apply_merges_and_restore_is_byte_exact(self):
        s = cs.ConfigStore("r1")
        s.apply("pub/repo/a.gguf", SETTINGS)
        s.apply("pub/repo/a.gguf", dict(SETTINGS, threads=8, kv_quant=None))  # 2nd write, same backup
        s.apply("pub/repo/b.gguf", SETTINGS)
        f = self.fields(self.existing)
        self.assertEqual(f["user.custom"], 7)
        self.assertEqual(f["llm.load.llama.cpuThreadPoolSize"], 8)
        self.assertFalse(f["llm.load.llama.kCacheQuantizationType"]["checked"])
        done, problems = cs.ConfigStore.restore_all()
        self.assertEqual(problems, [])
        self.assertEqual(self.existing.read_bytes(), self.original)
        self.assertFalse(self.absent.exists())
        self.assertFalse(cs.JOURNAL.exists())

    def test_recover_after_killed_run(self):
        cs.ConfigStore("r1").apply("pub/repo/a.gguf", SETTINGS)  # no restore: simulated crash
        cs.ConfigStore("r2").apply("pub/repo/a.gguf", dict(SETTINGS, threads=2))  # must keep 1st backup
        cs.ConfigStore.restore_all()
        self.assertEqual(self.existing.read_bytes(), self.original)

    def test_path_escape_refused(self):
        with self.assertRaises(RuntimeError):
            cs.ConfigStore("r1").apply("../../evil.gguf", SETTINGS)


if __name__ == "__main__":
    unittest.main()
