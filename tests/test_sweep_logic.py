"""Offline test of job planning, resume selection and invalidation (no GPU, no LM Studio)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runner"))
import sweep  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class SweepLogicTest(unittest.TestCase):
    def test_quick_grid_job_count_and_size_filter(self):
        grid = json.loads((ROOT / "configs" / "quick.json").read_text(encoding="utf-8"))
        meta = {k: {"paramsString": "14B" if ("14b" in k or "12b" in k) else "8B"} for k in grid["models"]}
        jobs = sweep.build_jobs(grid, grid["models"], meta)
        large = sum(1 for k in grid["models"] if meta[k]["paramsString"] == "14B")
        for_all = sum(1 for c in grid["configs"] if "only_params" not in c)
        self.assertGreater(large, 0)
        self.assertEqual(len(jobs), for_all * len(grid["models"]) + (len(grid["configs"]) - for_all) * large)
        self.assertEqual([j["n"] for j in jobs], list(range(1, len(jobs) + 1)))
        self.assertFalse(any(j["config"].startswith("off") for j in jobs if j["model"] == "qwen3-8b"))
        self.assertNotIn("only_params", jobs[-1]["settings"])

    def test_resume_selection(self):
        jobs = [{"n": i, "id": f"m|{i}"} for i in (1, 2, 3, 4)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            sweep.append_row(p, {"job_id": "m|1", "status": "ok"})
            sweep.append_row(p, {"job_id": "m|2", "status": "timeout"})
            sweep.append_row(p, {"job_id": "m|3", "status": "ok"})
            ids = lambda **kw: [j["n"] for j in sweep.todo_jobs(jobs, sweep.latest_results(p), **kw)]
            self.assertEqual(ids(), [4])  # failed jobs are NOT retried automatically
            self.assertEqual(ids(redo_failed=True), [2, 4])
            sweep.append_row(p, {"job_id": "m|3", "status": "invalidated"})  # resume --from 3
            self.assertEqual(ids(), [3, 4])


class RunnerAliveTest(unittest.TestCase):
    def status(self, age, **kw):
        return dict({"state": "running", "heartbeat": time.time() - age}, **kw)

    def test_fresh_heartbeat_and_end_states(self):
        self.assertTrue(sweep.runner_alive(self.status(1)))
        self.assertFalse(sweep.runner_alive(self.status(1, state="done")))
        self.assertFalse(sweep.runner_alive(None))

    @unittest.skipUnless(os.name == "nt", "process check is implemented for Windows")
    def test_late_heartbeat_trusts_only_the_same_process(self):
        pid, created = os.getpid(), sweep.process_created(os.getpid())
        self.assertIsNotNone(created)
        self.assertTrue(sweep.runner_alive(self.status(600, pid=pid, pid_created=created)))
        self.assertFalse(sweep.runner_alive(self.status(600, pid=pid, pid_created=created + 1)))  # PID reused
        self.assertFalse(sweep.runner_alive(self.status(600, pid=pid)))  # status without a creation time

    @unittest.skipUnless(os.name == "nt", "process check is implemented for Windows")
    def test_ended_process_is_gone(self):
        child = subprocess.Popen([sys.executable, "-c", "input()"], stdin=subprocess.PIPE)
        try:
            created = sweep.process_created(child.pid)
            self.assertIsNotNone(created)
        finally:
            child.communicate(b"\n", timeout=30)
        self.assertFalse(sweep.runner_alive(self.status(600, pid=child.pid, pid_created=created)))

    def test_watch_ends_only_after_two_finished_readings(self):
        readings = [("a", False), ("b", True), ("c", False), ("d", True), ("e", True)]
        with mock.patch.object(sweep, "status_text", side_effect=readings) as read, \
                mock.patch.object(sweep.os, "system"), mock.patch.object(sweep.time, "sleep"), \
                mock.patch("builtins.print"):
            self.assertEqual(sweep.main(["status", "--watch"]), 0)
        self.assertEqual(read.call_count, 5)


class PausedWaitTest(unittest.TestCase):
    """wait_paused with a faked GPU check, environment and clock sleep."""

    def wait(self, auto, ready, on_sleep=lambda n: None, retry=0.001):
        sleeps = []

        def sleep(_):
            sleeps.append(1)
            on_sleep(len(sleeps))
            self.assertLess(len(sleeps), 50, "wait_paused did not return")
            real_sleep(0.01)

        real_sleep = sweep.time.sleep
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(sweep, "CONTROL", Path(d) / "control.json"), \
                mock.patch.object(sweep, "environment", return_value={}), \
                mock.patch.object(sweep, "log"), \
                mock.patch.object(sweep.time, "sleep", sleep):
            sweep.write_json(sweep.CONTROL, {"cmd": "pause", "now": False, "ts": 1})
            runner = sweep.Runner("r", {"options": {"busy_retry_s": retry}, "env": {}}, mock.Mock())
            runner.ensure_ready = mock.Mock(side_effect=ready)
            result = runner.wait_paused("GPU busy", auto=auto)
            return result, sweep.control()["cmd"], runner.ensure_ready.call_count

    def test_busy_gpu_resumes_by_itself(self):
        ready = [sweep.Blocked("busy"), sweep.StepError("timeout", "lms ps"), None]
        self.assertEqual(self.wait(True, ready), ("run", "run", 3))

    def test_user_pause_turns_automatic_checks_off(self):
        def on_sleep(n):
            if n == 1:
                sweep.send("pause")
            if n == 5:
                sweep.send("stop")

        self.assertEqual(self.wait(True, [], on_sleep, retry=0.03), ("stop", "stop", 0))

    def test_manual_pause_never_resumes_by_itself(self):
        on_sleep = lambda n: n == 5 and sweep.send("stop")
        self.assertEqual(self.wait(False, [], on_sleep), ("stop", "stop", 0))


if __name__ == "__main__":
    unittest.main()
