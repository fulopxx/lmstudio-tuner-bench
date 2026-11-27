"""Offline tests of IF-23: every JSON data file an interface reads carries `schema_version`; a newer version stops the
reading with the file name; a file from before step D2e (no version) still reads."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import agent, agent_report, runs, runstate, sweep  # noqa: E402
from bench.core.progress import CoreError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = os.name == "nt"


class StateDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        self.patches = [mock.patch.object(runstate, "STATE", root / "state"), mock.patch.object(sweep, "ROOT", root)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()

    def version(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8")).get("schema_version")


class WrittenFilesTest(StateDirTest):
    def test_state_files_carry_the_version(self):
        runstate.new_run_dir("r")
        runstate.init_files("r")
        runstate.Status("r", {"kind": "sweep", "state": "running"}).close(state="stopped")
        self.assertEqual(self.version(runstate.control_path("r")), 1)
        self.assertEqual(self.version(runstate.status_path("r")), 1)
        runs.close_run("r")
        self.assertEqual(self.version(runstate.status_path("r")), 1)

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_lock_carries_the_version(self):
        runstate.acquire("r", "sweep")
        try:
            self.assertEqual(self.version(runstate.active_path()), 1)
        finally:
            runstate.release("r")

    def test_plan_carries_the_version(self):
        with mock.patch.object(sweep, "plan_run", return_value={"jobs": []}), \
                mock.patch.object(sweep, "environment", return_value={}), \
                mock.patch.object(sweep, "execute", return_value=0):
            run_id = sweep.start_run("grid.json", None, {k: 1 for k in sweep.RUN_OPTIONS})["run"]
        self.assertEqual(self.version(runstate.run_dir(run_id) / "plan.json"), 1)


class ReadingTest(StateDirTest):
    def test_newer_versions_stop_the_reading_with_the_file_name(self):
        runstate.new_run_dir("r")
        for path in (runstate.status_path("r"), runstate.control_path("r"), runstate.run_dir("r") / "plan.json"):
            with self.subTest(file=path.name):
                runstate.write_json(path, {"schema_version": 99, "state": "running", "cmd": "run", "jobs": []})
                with self.assertRaisesRegex(CoreError, f"{path.name}: format version 99 is newer"):
                    {"status.json": lambda: runstate.read_status("r"), "control.json": lambda: runstate.control("r"),
                     "plan.json": lambda: runs.describe("r", "sweep")}[path.name]()
                path.unlink()
        runstate.write_json(runstate.active_path(), {"schema_version": 2, "run": "x"})
        with self.assertRaisesRegex(CoreError, "active.json"):
            runstate.active()

    def test_files_from_before_d2e_still_read(self):
        runstate.new_run_dir("old")
        runstate.write_json(runstate.run_dir("old") / "plan.json", {"jobs": [{"n": 1, "id": "m|c", "model": "m",
                                                                             "config": "c"}]})
        runstate.write_json(runstate.status_path("old"), {"run": "old", "kind": "sweep", "state": "stopped",
                                                          "heartbeat": time.time() - 600})
        runstate.write_json(runstate.control_path("old"), {"cmd": "stop", "now": False, "ts": 1})
        self.assertEqual(runstate.read_status("old")["state"], "stopped")
        self.assertEqual(runstate.control("old")["cmd"], "stop")
        item = runs.describe("old")
        self.assertEqual((item["state"], item["total"]), ("stopped", 1))
        runs.close_run("old")  # writing gives the file the current version
        self.assertEqual(self.version(runstate.status_path("old")), 1)


@unittest.skipIf(agent.harness_problem(), f"agent harness: {agent.harness_problem()}")
class AgentReportTest(unittest.TestCase):
    def test_report_carries_the_version_and_a_newer_one_is_refused(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(runstate, "STATE", Path(d)):
            options = cli.agent_parser().parse_args(["run", "--repeats", "1", "--scripted",
                                                     str(ROOT / "tests" / "agent_scripted.json")])
            run = agent.run_tasks(options)["run"]
            try:
                result = agent.report([run])
                self.assertEqual(result["data"]["schema_version"], 1)
                result["path"].with_suffix(".json").write_text(json.dumps(dict(result["data"], schema_version=2)),
                                                                encoding="utf-8")
                with mock.patch.object(agent_report, "write", return_value=result["path"]):  # keep the newer file
                    with self.assertRaisesRegex(CoreError, "format version 2 is newer"):
                        agent.report([run])
            finally:
                (ROOT / "results" / f"agent_{run}.jsonl").unlink(missing_ok=True)
                shutil.rmtree(ROOT / "results" / "agent" / run, ignore_errors=True)
                for suffix in (".md", ".json"):
                    (ROOT / "report" / f"agent_{run}{suffix}").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
