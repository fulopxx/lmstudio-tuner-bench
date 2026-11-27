"""Model registry (CR-20 to CR-24), offline with made-up `lms ls` records."""
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import models, sweep  # noqa: E402
from bench.core.progress import CoreError  # noqa: E402


def record(arch, params, vision=False, tools=True, kind="llm"):
    return {"type": kind, "architecture": arch, "paramsString": params, "quantization": {"name": "Q4_K_M", "bits": 4},
            "vision": vision, "trainedForToolUse": tools, "maxContextLength": 32768, "sizeBytes": 5_000_000_000}


CATALOG = {"qwen3-8b": record("qwen3", "8B"), "qwen3.5-4b-mtp": record("qwen35", "4B", vision=True),
           "qwen2.5-coder-7b-instruct": record("qwen2", "7B", tools=False)}


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name)
        self.snapshot = d / "models.json"
        self.tags = d / "models.local.json"

    def tearDown(self):
        self.dir.cleanup()

    def refresh(self, catalog, now=None):
        return models.refresh(catalog, self.snapshot, now)

    def test_snapshot_has_the_capability_fields(self):
        result = self.refresh(CATALOG)
        self.assertEqual((result["count"], result["first_snapshot"]), (3, True))
        data = json.loads(self.snapshot.read_text(encoding="utf-8"))
        fields = data["models"]["qwen3.5-4b-mtp"]
        self.assertEqual(set(fields), set(models.FIELDS) | set(models.DATES))
        self.assertTrue(fields["baseline"])
        self.assertEqual((fields["vision"], fields["tool_use"], fields["params"], fields["quantization"],
                          fields["max_context"]), (True, True, "4B", "Q4_K_M", 32768))

    def test_own_tags_override_generated_fields(self):
        self.refresh(CATALOG)
        self.tags.write_text(json.dumps({"qwen3.5-4b-mtp": {"mtp": True, "vision": False}}), encoding="utf-8")
        reg = models.registry(self.snapshot, self.tags)
        self.assertTrue(reg["qwen3.5-4b-mtp"]["mtp"])
        self.assertFalse(reg["qwen3.5-4b-mtp"]["vision"])
        self.tags.write_text(json.dumps({"qwen3-8b": ["mtp"]}), encoding="utf-8")
        with self.assertRaises(CoreError):
            models.registry(self.snapshot, self.tags)

    def test_new_models_by_first_date(self):
        day = datetime(2026, 11, 27, 12, 0)
        self.refresh({k: v for k, v in CATALOG.items() if k != "qwen3-8b"}, day)
        self.assertEqual(models.new_models(snapshot=self.snapshot, now=day), [])  # the first snapshot is the baseline
        result = self.refresh(CATALOG, day + timedelta(hours=1))
        self.assertEqual(result["appeared"], ["qwen3-8b"])
        # a later refresh keeps the model new, until the days have passed
        self.refresh(CATALOG, day + timedelta(days=2))
        self.assertEqual(models.new_models(snapshot=self.snapshot, now=day + timedelta(days=2)), ["qwen3-8b"])
        self.assertEqual(models.new_models(snapshot=self.snapshot, now=day + timedelta(days=9)), [])
        self.assertEqual(models.new_models(30, self.snapshot, day + timedelta(days=9)), ["qwen3-8b"])

    def test_gone_model_keeps_its_first_date(self):
        day = datetime(2026, 11, 27, 12, 0)
        self.refresh({k: v for k, v in CATALOG.items() if k != "qwen3-8b"}, day)
        self.refresh(CATALOG, day + timedelta(hours=1))
        first = json.loads(self.snapshot.read_text(encoding="utf-8"))["models"]["qwen3-8b"]["first_seen"]
        result = self.refresh({k: v for k, v in CATALOG.items() if k != "qwen3-8b"}, day + timedelta(days=1))
        self.assertEqual(result["disappeared"], ["qwen3-8b"])
        data = json.loads(self.snapshot.read_text(encoding="utf-8"))
        self.assertIn("gone_since", data["gone"]["qwen3-8b"])
        self.refresh(CATALOG, day + timedelta(days=2))
        data = json.loads(self.snapshot.read_text(encoding="utf-8"))
        self.assertEqual(data["models"]["qwen3-8b"]["first_seen"], first)
        self.assertNotIn("qwen3-8b", data["gone"])

    def test_format_1_snapshot_becomes_the_baseline(self):
        self.snapshot.write_text(json.dumps({"schema_version": 1, "taken": "2026-11-27T10:00:00", "models": {
            "qwen3-8b": models.entry(CATALOG["qwen3-8b"])}}), encoding="utf-8")
        reg = models.registry(self.snapshot, self.tags)
        self.assertFalse(reg["qwen3-8b"]["new"])
        self.assertEqual(reg["qwen3-8b"]["first_seen"], "2026-11-27T10:00:00")

    def test_selection_by_capability(self):
        self.refresh(CATALOG)
        reg = models.registry(self.snapshot, self.tags)
        self.assertEqual(models.select("tool_use", None, reg), ["qwen3-8b", "qwen3.5-4b-mtp"])
        self.assertEqual(models.select("tool_use,!vision", None, reg), ["qwen3-8b"])
        self.assertEqual(models.select("architecture=QWEN2", None, reg), ["qwen2.5-coder-7b-instruct"])
        self.assertEqual(models.select("tool_use", ["qwen3.5-4b-mtp", "qwen3-8b"], reg),
                         ["qwen3.5-4b-mtp", "qwen3-8b"])
        with self.assertRaises(CoreError):
            models.select("vision,!tool_use", None, reg)
        with self.assertRaises(CoreError):
            models.select("tool_use", ["unknown-model"], reg)

    def test_missing_snapshot_is_a_clear_error(self):
        with self.assertRaises(CoreError) as e:
            models.registry(self.snapshot, self.tags)
        self.assertIn("bench models refresh", str(e.exception))


class FilterInRunsTest(unittest.TestCase):
    """CR-24 through the command line: the filter picks the models, an empty selection stops the run."""

    def setUp(self):
        self.reg = {k: models.entry(v) for k, v in CATALOG.items()}

    def test_sweep_dry_run_uses_the_selection(self):
        catalog = {k: {**v, "modelKey": k, "path": f"x/{k}.gguf"} for k, v in CATALOG.items()}
        out = io.StringIO()
        with mock.patch.object(models, "registry", return_value=self.reg), \
                mock.patch.object(models, "refresh") as refresh, \
                mock.patch.object(sweep, "model_catalog", return_value=catalog), \
                mock.patch.object(sweep, "environment", return_value={"runtime": "cuda"}), redirect_stdout(out):
            code = cli.main(["run", "--dry-run", "--grid", str(Path(sweep.ROOT) / "configs" / "validate.json"),
                             "--where", "!tool_use"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("qwen2.5-coder-7b-instruct", out.getvalue())
        self.assertNotIn("qwen3-8b", out.getvalue())
        refresh.assert_called_once()  # the registry is refreshed before the selection

    @unittest.skipIf(cli.agent.harness_problem(), "agent harness not installed")
    def test_empty_selection_stops_the_agent_run(self):
        out = io.StringIO()
        with mock.patch.object(models, "registry", return_value=self.reg), \
                mock.patch.object(models, "refresh", side_effect=OSError("lms not found")), redirect_stdout(out):
            code = cli.main(["agent", "run", "--where", "vision,!tool_use"])
        self.assertEqual(code, 3)
        self.assertIn("no model matches", out.getvalue())
        self.assertIn("not refreshed", out.getvalue())  # without LM Studio the stored registry is used


if __name__ == "__main__":
    unittest.main()
