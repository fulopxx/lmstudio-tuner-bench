"""Offline tests of the progress log, the request source and the agent stop through the control file (IF-12, IF-14,
IF-15)."""
import io
import json
import os
import queue
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import agent, progress, runstate, sweep  # noqa: E402
from bench.core.progress import CoreError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = os.name == "nt"


class StateDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(runstate, "STATE", Path(self.dir.name))
        self.patch.start()
        agent.USER_STOP.clear()
        progress.set_sink(None)  # cli.main in another test leaves its printing sink behind

    def tearDown(self):
        agent.USER_STOP.clear()
        self.patch.stop()
        self.dir.cleanup()

    def active_run(self, kind, run="busy"):
        """A living run of this process, as `bench status` and the control commands see it."""
        runstate.new_run_dir(run)
        runstate.init_files(run)
        runstate.write_json(runstate.active_path(), {"run": run, "kind": kind, "pid": os.getpid(),
                                                     "pid_created": runstate.process_created(os.getpid())})
        runstate.write_json(runstate.status_path(run), {"run": run, "kind": kind, "state": "running",
                                                        "heartbeat": time.time()})
        return run


class ProgressLogTest(StateDirTest):
    def test_every_line_goes_to_the_log_and_threads_do_not_mix_lines(self):
        runstate.new_run_dir("r")
        runstate.init_files("r")
        seen = []
        progress.set_sink(seen.append)
        try:
            with runstate.logging_to("r"):
                progress.emit("first\nsecond")
                threads = [threading.Thread(target=lambda i=i: [progress.emit(f"t{i} line {k}") for k in range(50)])
                           for i in range(4)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
            progress.emit("after the run")
        finally:
            progress.set_sink(None)
        lines = runstate.log_path("r").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:2], ["first", "second"])
        self.assertEqual(sorted(lines[2:]), sorted(f"t{i} line {k}" for i in range(4) for k in range(50)))
        self.assertNotIn("after the run", lines)
        self.assertIn("after the run", seen)  # the sink still gets every line

    @unittest.skipIf(agent.harness_problem(), f"agent harness: {agent.harness_problem()}")
    def test_scripted_agent_run_logs_core_and_harness_lines(self):
        a = cli.agent_parser().parse_args(["run", "--repeats", "1", "--scripted",
                                           str(ROOT / "tests" / "agent_scripted.json")])
        with mock.patch.object(agent, "ROOT", Path(self.dir.name)):
            result = agent.run_tasks(a)
        text = runstate.log_path(result["run"]).read_text(encoding="utf-8")
        self.assertIn(f" run {result['run']}, scripted:", text)
        self.assertRegex(text, r"(?m)^\d\d:\d\d:\d\d   \S")  # a harness line, stamped and indented


class RequestSourceTest(StateDirTest):
    def test_source_is_recorded_and_shown(self):
        run = self.active_run("sweep")
        result = sweep.request_control("pause", now=True, source="web")
        self.assertEqual((result["source"], runstate.control(run)["source"]), ("web", "web"))
        st = sweep.run_status()
        self.assertEqual((st["last_request"]["cmd"], st["last_request"]["source"]), ("pause", "web"))
        self.assertRegex("\n".join(cli.request_lines(st)), r"last request: pause --now from web at \d\d:\d\d:\d\d")

    def test_cli_is_the_default_source_and_unknown_sources_are_refused(self):
        run = self.active_run("sweep")
        sweep.request_control("stop")
        self.assertEqual(runstate.control(run)["source"], "cli")
        with self.assertRaises(CoreError):
            runstate.send(run, "stop", source="browser")

    def test_the_run_start_is_not_shown_as_a_request(self):
        run = self.active_run("sweep")
        self.assertEqual(runstate.control(run)["source"], "runner")
        self.assertEqual(cli.request_lines(sweep.run_status()), [])

    def test_runner_sees_the_source(self):
        runstate.new_run_dir("r")
        runstate.send("r", "stop", now=True, source="web")
        runner = sweep.Runner("r", {"options": {}, "env": {}}, mock.Mock())
        with self.assertRaises(sweep.Interrupted) as e:
            runner.checkpoint()
        self.assertEqual((e.exception.cmd, e.exception.source), ("stop", "web"))


class FakeHarness:
    """Stands in for the node process: runs until a stop command arrives on stdin, then prints its RESULT."""

    def __init__(self):
        self.out = queue.Queue()
        self.stop_at = None
        self.returncode = None
        test = self

        class Stdin:
            def write(self, text):
                if json.loads(text).get("cmd") == "stop" and test.stop_at is None:
                    test.stop_at = time.time()
                    test.out.put('RESULT: {"attempts": [], "stopped": true}\n')
                    test.out.put(None)

            def flush(self):
                pass

            def close(self):
                pass

        class Lines:
            def __iter__(self):
                while True:
                    line = test.out.get()
                    if line is None:
                        return
                    yield line

            def close(self):
                pass

        self.stdin, self.stdout = Stdin(), Lines()
        self.stderr = type("Empty", (), {"__iter__": lambda s: iter(()), "close": lambda s: None})()

    def poll(self):
        if self.stop_at is not None:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        end = time.time() + (timeout or 0)
        while time.time() < end and self.poll() is None:
            time.sleep(0.02)
        if self.poll() is None:
            raise agent.subprocess.TimeoutExpired("node", timeout)
        return 0

    def kill(self):
        self.returncode = -9


class AgentStopTest(StateDirTest):
    def test_stop_in_the_control_file_reaches_the_harness_within_2_s(self):
        runstate.new_run_dir("r")
        runstate.init_files("r")
        harness = FakeHarness()
        asked = {}

        def ask_stop():
            time.sleep(0.3)
            asked["at"] = time.time()
            runstate.send("r", "stop", source="web")

        threading.Thread(target=ask_stop, daemon=True).start()
        with mock.patch.object(agent.subprocess, "Popen", return_value=harness), \
                mock.patch.object(agent.machine, "node_env", return_value={}):
            result = agent.run_harness({"spec": 1}, timeout_s=60, run_id="r")
        self.assertTrue(result["stopped"])
        self.assertLess(harness.stop_at - asked["at"], 2.0)
        self.assertTrue(agent.USER_STOP.is_set())

    def test_stop_during_the_load_starts_no_harness(self):
        runstate.new_run_dir("r")
        runstate.send("r", "stop", source="cli")
        a = cli.agent_parser().parse_args(["run", "--repeats", "1", "--scripted",
                                           str(ROOT / "tests" / "agent_scripted.json")])
        data, digest = agent.load_tasks(a.tasks)
        with mock.patch.object(agent, "run_harness", side_effect=AssertionError("harness started")):
            attempts, summary, _ = agent.run_model(a, "scripted", data, digest, data["tasks"], "r",
                                                   Path(self.dir.name) / "out", 60)
        self.assertEqual((attempts, summary["stopped"]), ([], True))

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_agent_run_can_be_stopped_but_not_paused(self):
        run = self.active_run("agent")
        with self.assertRaises(CoreError):
            sweep.request_control("pause")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["stop"]), 0)
        self.assertIn(f"agent run {run}", out.getvalue())
        self.assertEqual((runstate.control(run)["cmd"], runstate.control(run)["source"]), ("stop", "cli"))
        self.assertEqual(sweep.run_status()["requested"]["cmd"], "stop")


if __name__ == "__main__":
    unittest.main()
