"""Result format (CR-10 to CR-14) and machine settings (CR-15), offline."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.core import evaluate, machine, results, sweep  # noqa: E402
from bench.core.progress import CoreError  # noqa: E402

ENV = {"gpu": "GPU X", "vram_total_mib": 8192, "driver": "1.0", "lmstudio_app": None, "runtime": "rt@1",
       "sdk": "2.1.0", "harness": "0.2.0", "os": "os", "python": "3", "node": "26"}


class EnvelopeTest(unittest.TestCase):
    def test_new_row_carries_version_kind_and_env(self):
        row = results.envelope("sweep", "r1", {"job_id": "m|c", "status": "ok", "app_version": "1.2.0"}, ENV)
        self.assertEqual(list(row)[:3], ["schema_version", "kind", "run"])
        self.assertEqual((row["schema_version"], row["kind"], row["run"]), (results.SCHEMA_VERSION, "sweep", "r1"))
        self.assertEqual(set(row["env"]), set(results.ENV_KEYS))
        self.assertEqual(row["env"]["lmstudio_app"], "1.2.0")

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            results.envelope("quality", "r1", {}, ENV)


class MigrationTest(unittest.TestCase):
    def test_old_agent_row(self):
        old = {"schema_version": 2, "run": "r", "model": "m", "task": "t", "attempt": 1, "app_version": "1.2.0",
               "env": {"runtime": "rt@1", "driver": "617", "loader": "@lmstudio/sdk 2.1.0"}}
        new = results.migrate(old)
        self.assertEqual((new["kind"], new["schema_version"], new["tasks_schema_version"]), ("agent", 1, 2))
        self.assertEqual((new["env"]["runtime"], new["env"]["driver"], new["env"]["sdk"]), ("rt@1", "617", "2.1.0"))
        self.assertEqual(new["env"]["lmstudio_app"], "1.2.0")
        self.assertIsNone(new["env"]["gpu"])
        self.assertEqual(new["migrated_from"], 0)

    def test_old_sweep_row_and_unknown_runtime(self):
        new = results.migrate({"job_id": "m|c", "run": "r", "status": "ok", "runtime": "?", "driver": "617"})
        self.assertEqual(new["kind"], "sweep")
        self.assertIsNone(new["env"]["runtime"])
        self.assertEqual(new["env"]["driver"], "617")
        self.assertNotIn("tasks_schema_version", new)

    def test_reading_does_not_rewrite_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sweep_r.jsonl"
            text = json.dumps({"job_id": "m|c", "run": "r", "status": "invalidated"}) + "\n"
            p.write_text(text, encoding="utf-8")
            rows = results.read_rows(p)
            self.assertEqual(rows[0]["kind"], "sweep")
            self.assertEqual(p.read_text(encoding="utf-8"), text)
            self.assertEqual(sweep.latest_results(p)["m|c"]["status"], "invalidated")
            self.assertEqual(evaluate.load_rows(p), [])

    def test_newer_format_is_refused_with_file_and_version(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "agent_r.jsonl"
            p.write_text(json.dumps({"schema_version": results.SCHEMA_VERSION + 1, "kind": "agent"}) + "\n",
                         encoding="utf-8")
            with self.assertRaises(CoreError) as e:
                results.read_rows(p)
            self.assertIn("agent_r.jsonl:1", str(e.exception))
            self.assertIn(str(results.SCHEMA_VERSION + 1), str(e.exception))


class MachineSettingsTest(unittest.TestCase):
    def test_defaults_follow_the_user_profile(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"USERPROFILE": d}):
            s = machine.settings(Path(d) / "missing.json")
            self.assertEqual(s["lms"], str(Path(d) / ".lmstudio" / "bin" / "lms.exe"))
            self.assertTrue(s["api_file"].endswith("http-server.json"))
            self.assertEqual(s["configured"], [])

    def test_settings_file_overrides_and_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "machine.local.json"
            p.write_text(json.dumps({"lmstudio_dir": "X:/lms"}), encoding="utf-8")
            s = machine.settings(p)
            self.assertEqual(Path(s["lms"]), Path("X:/lms/bin/lms.exe"))
            self.assertEqual(s["configured"], ["lmstudio_dir"])
            p.write_text(json.dumps({"lms_dir": "X:/lms"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                machine.settings(p)

    def test_node_env_sets_the_api_file_only_when_configured(self):
        with mock.patch.object(machine, "settings", return_value={"api_file": "A", "configured": []}), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LMS_API_FILE", None)
            self.assertNotIn("LMS_API_FILE", machine.node_env())
        with mock.patch.object(machine, "settings", return_value={"api_file": "A", "configured": ["api_file"]}):
            self.assertEqual(machine.node_env()["LMS_API_FILE"], "A")

    def test_fingerprint_without_tools_has_nones_not_guesses(self):
        with mock.patch.object(machine, "_run", return_value=None):
            env = machine.fingerprint(refresh=True)
        try:
            self.assertEqual((env["gpu"], env["vram_total_mib"], env["driver"], env["runtime"], env["node"]),
                             (None, None, None, None, None))
            self.assertIsNotNone(env["python"])
        finally:
            machine.fingerprint(refresh=True)


if __name__ == "__main__":
    unittest.main()
