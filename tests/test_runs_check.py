"""Offline tests of `bench check` (IF-20), `bench runs` (IF-21) and `bench close` (IF-22)."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import agent, check, progress, results, runs, runstate, sweep  # noqa: E402
from bench.core.progress import CoreError  # noqa: E402

WINDOWS = os.name == "nt"
IDLE = [[1000, 16000, 2]] * 3


class AssessTest(unittest.TestCase):
    def levels(self, loaded, samples=IDLE, leftover_ok=True):
        return {f["check"]: f["level"] for f in check.assess(loaded, samples, 3500, 30, leftover_ok)}

    def test_rules(self):
        self.assertEqual(self.levels([]), {"loaded_models": "ok", "free_vram_mib": "ok", "gpu_util_pct": "ok"})
        self.assertEqual(self.levels(["bench-sweep"])["loaded_models"], "warn")
        self.assertEqual(self.levels(["bench-sweep"], leftover_ok=False)["loaded_models"], "fail")
        self.assertEqual(self.levels(["my-model"])["loaded_models"], "fail")
        self.assertEqual(self.levels([], [[14000, 16000, 2]] * 3)["free_vram_mib"], "fail")
        self.assertEqual(self.levels([], [[1000, 16000, 90], [1000, 16000, 50], [1000, 16000, 10]])["gpu_util_pct"],
                         "fail")  # median 50 > 30

    def test_text_of_lms_ps(self):
        self.assertEqual(check.loaded_from_text("No models are currently loaded.\n"), [])
        self.assertEqual(check.loaded_from_text("bench-agent  qwen3-8b  ..."), ["bench-agent"])
        self.assertEqual(check.loaded_from_text("someone-else  model"), ["?"])


class StateDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        self.patches = [mock.patch.object(runstate, "STATE", root / "state"), mock.patch.object(sweep, "ROOT", root)]
        for p in self.patches:
            p.start()
        (root / "results").mkdir()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()
        progress.set_sink(None)

    def sweep_run(self, run_id, done, total, status=None):
        runstate.new_run_dir(run_id)
        jobs = [{"n": i, "id": f"m|c{i}", "model": "m", "config": f"c{i}"} for i in range(1, total + 1)]
        runstate.write_json(runstate.run_dir(run_id) / "plan.json", {"jobs": jobs})
        for j in jobs[:done]:
            sweep.append_row(sweep.ROOT / "results" / f"sweep_{run_id}.jsonl",
                             results.envelope("sweep", run_id, {"job_id": j["id"], "status": "ok"}, {}))
        if status:
            runstate.write_json(runstate.status_path(run_id), {"run": run_id, "kind": "sweep", **status})

    def agent_results(self, run_id, attempts):
        for i in range(attempts):
            sweep.append_row(sweep.ROOT / "results" / f"agent_{run_id}.jsonl",
                             results.envelope("agent", run_id, {"task": "t", "attempt": i + 1}, {}))


class MachineCheckTest(StateDirTest):
    def run_check(self, ps_json="[]"):
        calls = []

        def sh(cmd, timeout):
            calls.append(cmd)
            return 0, ps_json

        with mock.patch.object(check, "sh", sh), mock.patch.object(sweep, "gpu_state", return_value=IDLE[0]), \
                mock.patch.object(sweep, "environment", return_value={"runtime": "llama.cpp-cuda13@2.83.0"}), \
                mock.patch.object(agent, "harness_problem", return_value=None), \
                mock.patch.object(check.time, "sleep"):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["check", "--json"])
        return code, json.loads(out.getvalue()), calls

    def test_ready_machine(self):
        code, doc, _ = self.run_check()
        self.assertEqual((code, doc["ready"]), (0, True))
        self.assertEqual({f["check"] for f in doc["findings"]},
                         {"lms", "loaded_models", "free_vram_mib", "gpu_util_pct", "runtime", "harness", "active_run"})

    def test_a_left_over_model_is_only_reported(self):
        code, doc, calls = self.run_check('[{"identifier": "bench-sweep"}]')
        self.assertEqual(code, 0)
        self.assertEqual(next(f for f in doc["findings"] if f["check"] == "loaded_models")["level"], "warn")
        self.assertFalse(any("unload" in c for c in calls))  # read only

    def test_foreign_model_is_a_failure_with_exit_code_1(self):
        code, doc, _ = self.run_check('[{"identifier": "my-chat"}]')
        self.assertEqual((code, doc["ready"]), (1, False))

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_an_active_run_is_a_failure(self):
        runstate.acquire("busy", "agent")
        try:
            code, doc, _ = self.run_check()
        finally:
            runstate.release("busy")
        self.assertEqual(code, 1)
        self.assertIn("agent run busy", next(f for f in doc["findings"] if f["check"] == "active_run")["detail"])

    def test_runners_keep_their_messages(self):
        runner = sweep.Runner("r", {"options": {"min_free_mib": 3500, "max_util": 30}, "env": {}}, mock.Mock())
        with mock.patch.object(sweep, "sh", return_value=(0, "other-model  ...")):
            with self.assertRaisesRegex(sweep.Blocked, "a model is loaded that this run did not load"):
                runner.ensure_ready()
        with mock.patch.object(sweep, "sh", return_value=(0, "No models are currently loaded.")), \
                mock.patch.object(sweep, "gpu_state", return_value=[14000, 16000, 0]), \
                mock.patch.object(sweep.time, "sleep"):
            with self.assertRaisesRegex(sweep.Blocked, "only 2000 MiB VRAM free"):
                runner.ensure_ready()
        with mock.patch.object(agent, "sh", return_value=(0, "No models are currently loaded.")), \
                mock.patch.object(sweep, "gpu_state", return_value=[1000, 16000, 80]):
            with self.assertRaisesRegex(agent.StepError, "GPU 80% busy"):
                agent.machine_ready(3500, 30)


class RunsTest(StateDirTest):
    def states(self):
        return {r["run"]: r["state"] for r in runs.list_runs()["runs"]}

    def test_states_of_every_kind_of_run(self):
        self.sweep_run("20260101_000001", 2, 2)  # no status file, every job done
        self.sweep_run("20260101_000002", 1, 2)  # no status file, unfinished
        self.sweep_run("20260101_000003", 1, 2, {"state": "stopped"})
        self.sweep_run("20260101_000004", 1, 2, {"state": "running", "heartbeat": time.time() - 600})
        self.sweep_run("20260101_000005", 1, 2, {"state": "running", "heartbeat": time.time()})
        self.agent_results("20260101_000006", 3)
        self.assertEqual(self.states(), {"20260101_000001": "done", "20260101_000002": "unknown",
                                         "20260101_000003": "stopped", "20260101_000004": "gone",
                                         "20260101_000005": "running", "20260101_000006": "unknown"})
        listed = {r["run"]: r for r in runs.list_runs()["runs"]}
        self.assertEqual((listed["20260101_000002"]["done"], listed["20260101_000002"]["total"]), (1, 2))
        self.assertEqual((listed["20260101_000006"]["kind"], listed["20260101_000006"]["done"]), ("agent", 3))
        self.assertEqual(listed["20260101_000001"]["started"], "2026-01-01T00:00:01")


class CloseTest(StateDirTest):
    def test_close_an_unfinished_run_and_keep_its_files(self):
        self.sweep_run("20260101_000003", 1, 2, {"state": "stopped"})
        before = {p.name: p.read_bytes() for p in runstate.run_dir("20260101_000003").iterdir() if p.name != "status.json"}
        result = runs.close_run("20260101_000003", "not needed")
        self.assertEqual((result["state"], result["closed_from"]), ("closed", "stopped"))
        st = runstate.read_status("20260101_000003")
        self.assertEqual((st["state"], st["closed_from"], st["reason"]), ("closed", "stopped", "not needed"))
        after = {p.name: p.read_bytes() for p in runstate.run_dir("20260101_000003").iterdir() if p.name != "status.json"}
        self.assertEqual(after, before)
        self.assertTrue((sweep.ROOT / "results" / "sweep_20260101_000003.jsonl").exists())
        self.assertTrue(runs.close_run("20260101_000003")["already_closed"])
        self.assertEqual(self.states_of("20260101_000003"), "closed")

    def states_of(self, run_id):
        return next(r["state"] for r in runs.list_runs()["runs"] if r["run"] == run_id)

    def test_gone_and_old_agent_runs_can_be_closed(self):
        self.sweep_run("20260101_000004", 1, 2, {"state": "running", "heartbeat": time.time() - 600})
        self.assertEqual(runs.close_run("20260101_000004")["closed_from"], "gone")
        self.agent_results("20260101_000006", 3)
        self.assertEqual(runs.close_run("20260101_000006")["closed_from"], "unknown")
        self.assertEqual(runstate.read_status("20260101_000006")["kind"], "agent")

    def test_done_living_and_unknown_runs_are_refused(self):
        self.sweep_run("20260101_000001", 2, 2)
        self.sweep_run("20260101_000005", 1, 2, {"state": "running", "heartbeat": time.time()})
        for run_id, text in (("20260101_000001", "is done"), ("20260101_000005", "is active"),
                             ("20990101_000000", "no run")):
            with self.subTest(run=run_id), self.assertRaisesRegex(CoreError, text):
                runs.close_run(run_id)

    def test_a_closed_run_is_never_resumed(self):
        self.sweep_run("20260101_000003", 1, 2, {"state": "stopped"})
        sweep.latest_path().write_text("20260101_000003")
        runs.close_run("20260101_000003")
        with self.assertRaisesRegex(CoreError, "closed \\(the latest sweep\\)"):
            sweep.resume_run()
        with self.assertRaisesRegex(CoreError, "is closed"):
            sweep.resume_run("20260101_000003")

    def test_cli(self):
        self.sweep_run("20260101_000003", 1, 2, {"state": "stopped"})
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["close", "20260101_000003", "--json"]), 0)
            self.assertEqual(cli.main(["runs"]), 0)
            self.assertEqual(cli.main(["close", "20990101_000000"]), 2)
        text = out.getvalue()
        self.assertIn('"closed_from": "stopped"', text)
        self.assertRegex(text, r"20260101_000003\s+sweep\s+closed")


if __name__ == "__main__":
    unittest.main()
