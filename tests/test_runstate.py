"""Offline tests of the per-run state files and of the lock that allows one GPU run at a time (IF-10, IF-11, IF-13)."""
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import agent, runstate, sweep  # noqa: E402
from bench.core.progress import CoreError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = os.name == "nt"


class StateDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(runstate, "STATE", Path(self.dir.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dir.cleanup()


@unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
class LockTest(StateDirTest):
    def test_second_run_is_refused_with_the_active_run_named(self):
        runstate.acquire("20260101_000000", "sweep")
        with self.assertRaises(CoreError) as e:
            runstate.acquire("20260101_000001", "agent")
        self.assertIn("sweep run 20260101_000000", str(e.exception))
        self.assertEqual(runstate.active()["run"], "20260101_000000")
        runstate.release("20260101_000000")
        self.assertIsNone(runstate.active())
        runstate.acquire("20260101_000001", "agent")  # free again
        self.assertEqual(runstate.active()["kind"], "agent")

    def test_lock_of_an_ended_process_is_free(self):
        child = subprocess.Popen([sys.executable, "-c", "input()"], stdin=subprocess.PIPE)
        try:
            created = runstate.process_created(child.pid)
        finally:
            child.communicate(b"\n", timeout=30)
        runstate.write_json(runstate.active_path(), {"run": "old", "kind": "sweep", "pid": child.pid,
                                                     "pid_created": created})
        self.assertIsNone(runstate.active())
        runstate.acquire("new", "sweep")
        self.assertEqual(runstate.active()["run"], "new")

    def test_release_leaves_a_lock_of_another_run(self):
        runstate.acquire("a", "sweep")
        runstate.release("b")
        self.assertEqual(runstate.active()["run"], "a")


class RunFilesTest(StateDirTest):
    def test_new_run_gets_its_own_files(self):
        runstate.new_run_dir("r1")
        runstate.init_files("r1")
        status = runstate.Status("r1", {"kind": "sweep", "state": "running"})
        status.close(state="done")
        for name in ("status.json", "control.json", "progress.log"):
            self.assertTrue((runstate.run_dir("r1") / name).exists(), name)
        self.assertEqual(runstate.read_status("r1")["state"], "done")
        self.assertEqual(runstate.control("r1")["cmd"], "run")
        with self.assertRaises(CoreError):
            runstate.new_run_dir("r1")

    def test_a_new_run_leaves_the_files_of_an_older_one_alone(self):
        runstate.new_run_dir("r1")
        runstate.init_files("r1")
        runstate.Status("r1", {"kind": "sweep", "state": "stopped"}).close()
        before = {p.name: p.read_bytes() for p in runstate.run_dir("r1").iterdir()}
        runstate.new_run_dir("r2")
        runstate.init_files("r2")
        runstate.send("r2", "stop")
        runstate.Status("r2", {"kind": "agent", "state": "running"}).close(state="done")
        self.assertEqual({p.name: p.read_bytes() for p in runstate.run_dir("r1").iterdir()}, before)

    def test_new_run_id_skips_a_taken_second(self):
        taken = runstate.new_run_id()
        runstate.new_run_dir(taken)
        self.assertNotEqual(runstate.new_run_id(), taken)

    def test_shared_status_file_of_older_runs_is_still_read(self):
        runstate.write_json(runstate.legacy_status_path(), {"run": "old", "state": "done"})
        self.assertEqual(runstate.read_status("old")["state"], "done")
        self.assertIsNone(runstate.read_status("other"))


class RunsUseTheLockTest(StateDirTest):
    def hold_lock(self, kind):
        """A lock held by this test process, as another run would hold it."""
        runstate.write_json(runstate.active_path(), {"run": "busy", "kind": kind, "pid": os.getpid(),
                                                     "pid_created": runstate.process_created(os.getpid())})

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_sweep_is_refused_while_an_agent_run_holds_the_lock(self):
        self.hold_lock("agent")
        with mock.patch.object(sweep, "plan_run", return_value={"jobs": []}), \
                mock.patch.object(sweep, "execute") as execute:
            with self.assertRaises(CoreError) as e:
                sweep.start_run("grid.json", None, {k: 1 for k in sweep.RUN_OPTIONS})
        self.assertIn("agent run busy", str(e.exception))
        execute.assert_not_called()
        self.assertEqual(list((runstate.STATE / "runs").glob("*")) if (runstate.STATE / "runs").exists() else [], [])

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_agent_run_is_refused_while_a_sweep_holds_the_lock(self):
        self.hold_lock("sweep")
        out = io.StringIO()
        with mock.patch.object(agent, "harness_problem", lambda: None), \
                mock.patch.object(agent, "run_model") as run_model, redirect_stdout(out):
            code = cli.main(["agent", "run", "--model", "some-model"])
        self.assertEqual(code, 2)
        self.assertIn("sweep run busy", out.getvalue())
        run_model.assert_not_called()

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_pause_of_an_agent_run_is_refused(self):
        self.hold_lock("agent")
        runstate.write_json(runstate.status_path("busy"), {"run": "busy", "kind": "agent", "state": "running",
                                                           "heartbeat": time.time()})
        with self.assertRaises(CoreError):
            sweep.request_control("pause")

    def test_sweep_takes_and_gives_back_the_lock(self):
        seen = {}

        def execute(run_id, redo_failed=False):
            seen["lock"] = runstate.read_json(runstate.active_path())
            return 0

        with mock.patch.object(sweep, "plan_run", return_value={"jobs": []}), \
                mock.patch.object(sweep, "environment", return_value={}), \
                mock.patch.object(sweep, "execute", execute):
            result = sweep.start_run("grid.json", None, {k: 1 for k in sweep.RUN_OPTIONS})
        self.assertEqual((seen["lock"]["run"], seen["lock"]["kind"]), (result["run"], "sweep"))
        self.assertFalse(runstate.active_path().exists())
        self.assertTrue((runstate.run_dir(result["run"]) / "plan.json").exists())
        self.assertEqual(sweep.latest_run(), result["run"])

    def test_agent_run_state_after_a_scripted_run(self):
        def fake_run_model(a, model, data, task_hash, tasks, run_id, run_dir, timeout_s):
            seen["lock"] = runstate.read_json(runstate.active_path())
            seen["status"] = runstate.read_status(run_id)
            return [], {"attempts": [], "stopped": False}, {}

        seen = {}
        options = agent_options(scripted=str(ROOT / "tests" / "agent_scripted.json"))
        with mock.patch.object(agent, "harness_problem", lambda: None), \
                mock.patch.object(agent, "run_model", fake_run_model), \
                mock.patch.object(agent, "ROOT", Path(self.dir.name)):
            result = agent.run_tasks(options)
        self.assertIsNone(seen["lock"])  # a scripted run uses no GPU and takes no lock
        self.assertEqual((seen["status"]["kind"], seen["status"]["state"]), ("agent", "running"))
        final = runstate.read_status(result["run"])
        self.assertEqual((final["state"], final["current"]), ("done", None))
        for name in ("control.json", "progress.log"):
            self.assertTrue((runstate.run_dir(result["run"]) / name).exists(), name)

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_gpu_agent_run_holds_the_lock_and_ends_aborted_on_error(self):
        def fake_run_model(*args):
            seen["lock"] = runstate.read_json(runstate.active_path())
            raise RuntimeError("boom")

        seen = {}
        with mock.patch.object(agent, "harness_problem", lambda: None), \
                mock.patch.object(agent, "run_model", fake_run_model), \
                mock.patch.object(agent, "ROOT", Path(self.dir.name)):
            with self.assertRaises(RuntimeError):
                agent.run_tasks(agent_options(model="m"))
        self.assertEqual(seen["lock"]["kind"], "agent")
        self.assertFalse(runstate.active_path().exists())
        run_id = seen["lock"]["run"]
        final = runstate.read_status(run_id)
        self.assertEqual((final["state"], final["reason"]), ("aborted", "boom"))


def agent_options(**kw):
    a = cli.agent_parser().parse_args(["run", "--tasks", str(ROOT / "tasks" / "examples.json"), "--repeats", "1"])
    for k, v in kw.items():
        setattr(a, k, v)
    return a


if __name__ == "__main__":
    unittest.main()
