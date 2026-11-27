"""Offline tests of the --json output (IF-01): every command accepts it, prints exactly one JSON document that equals
the data of its core function, keeps its exit code, and sends progress lines to standard error."""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import agent, models, progress, results, runstate, sweep  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = os.name == "nt"


def run_cli(argv):
    """Runs the command line; returns (exit code, the one JSON document on standard output, standard error)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    progress.set_sink(None)
    return code, json.loads(out.getvalue()), err.getvalue()  # json.loads fails on anything but one document


def plain(data):
    """The core data as the --json output carries it."""
    return {"schema_version": cli.JSON_SCHEMA_VERSION, **json.loads(json.dumps(data, default=cli._plain))}


class EveryCommandTest(unittest.TestCase):
    def test_every_subcommand_accepts_json(self):
        for name, parser in (("bench", cli.sweep_parser()), ("bench agent", cli.agent_parser()),
                             ("bench models", cli.models_parser())):
            sub = next(a for a in parser._actions if a.dest == "cmd")
            for cmd, p in sub.choices.items():
                with self.subTest(command=f"{name} {cmd}"):
                    self.assertIn("--json", p._option_string_actions)


class StateDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(runstate, "STATE", Path(self.dir.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dir.cleanup()
        progress.set_sink(None)

    def active_run(self, kind, run="busy"):
        runstate.new_run_dir(run)
        runstate.init_files(run)
        runstate.write_json(runstate.active_path(), {"run": run, "kind": kind, "pid": os.getpid(),
                                                     "pid_created": runstate.process_created(os.getpid())})
        runstate.write_json(runstate.status_path(run), {"run": run, "kind": kind, "state": "running",
                                                        "heartbeat": time.time()})
        return run


class SweepCommandsTest(StateDirTest):
    def test_status_equals_the_core_data(self):
        code, doc, _ = run_cli(["status", "--json"])
        self.assertEqual((code, doc), (0, plain(sweep.run_status())))
        self.assertEqual(doc["schema_version"], 1)

    def test_watch_and_json_are_refused_as_json(self):
        code, doc, _ = run_cli(["status", "--watch", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(doc["error"]["code"], 2)
        self.assertIn("--watch", doc["error"]["message"])

    @unittest.skipUnless(WINDOWS, "the process check is implemented for Windows")
    def test_stop_of_an_agent_run(self):
        run = self.active_run("agent")
        code, doc, _ = run_cli(["stop", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual({k: doc[k] for k in ("run", "kind", "cmd", "source")}, {"run": run, "kind": "agent",
                                                                                "cmd": "stop", "source": "cli"})

    def test_refused_request_keeps_its_exit_code(self):
        code, doc, _ = run_cli(["pause", "--json"])
        self.assertEqual((code, doc), (2, {"schema_version": 1, "error": {"message": "no active run", "code": 2}}))

    def test_dry_run_gives_the_plan(self):
        catalog = {"m": {"path": "m.gguf", "paramsString": "1B"}}
        grid = str(ROOT / "configs" / "validate.json")
        with mock.patch.object(sweep, "model_catalog", return_value=catalog), \
                mock.patch.object(sweep, "environment", return_value={"runtime": "cuda"}):
            code, doc, err = run_cli(["run", "--dry-run", "--json", "--grid", grid, "--models", "m"])
            expected = plain(sweep.plan_run(grid, "m"))
        self.assertEqual((code, doc), (0, expected))
        self.assertEqual(err, "")

    def test_run_prints_one_document_and_keeps_the_exit_code(self):
        def execute(run_id, redo_failed=False):
            sweep.log("a progress line")
            return 3

        with mock.patch.object(sweep, "plan_run", return_value={"jobs": []}), \
                mock.patch.object(sweep, "environment", return_value={}), \
                mock.patch.object(sweep, "execute", execute):
            code, doc, err = run_cli(["run", "--json"])
        self.assertEqual((code, doc["exit_code"]), (3, 3))
        self.assertIn("a progress line", err)  # progress goes to standard error
        self.assertIn("a progress line", runstate.log_path(doc["run"]).read_text(encoding="utf-8"))

    def test_evaluate_gives_structured_data(self):
        with mock.patch.object(sweep, "ROOT", Path(self.dir.name)):
            path = Path(self.dir.name) / "results" / "sweep_r.jsonl"
            for cfg, decode in (("a", 50.0), ("b", 80.0)):
                row = {"job_id": f"m|{cfg}", "model": "m", "config": cfg, "status": "ok", "prompt_tok_s": 1000.0,
                       "decode_tok_s": decode, "settings": {"context_length": 4096}, "runs": []}
                sweep.append_row(path, results.envelope("sweep", "r", row, {}))
            code, doc, _ = run_cli(["evaluate", "--json", "--run", "r"])
            expected = plain(sweep.evaluate_run("r"))
        self.assertEqual((code, doc), (0, expected))
        self.assertEqual(doc["recommendations"][0]["config"], "b")
        self.assertIn("m", doc["analysis"])


class ModelsCommandsTest(unittest.TestCase):
    def test_list_and_its_error(self):
        reg = {"a": {"tool_use": True, "new": True}, "b": {"tool_use": False, "new": False}}
        with mock.patch.object(models, "registry", return_value=reg):
            code, doc, _ = run_cli(["models", "list", "--json", "--where", "tool_use"])
            self.assertEqual((code, doc), (0, plain(models.list_models("tool_use"))))
            self.assertEqual([m["key"] for m in doc["models"]], ["a"])
            code, doc, _ = run_cli(["models", "list", "--json", "--where", "vision"])
        self.assertEqual(code, 2)
        self.assertIn("no model matches", doc["error"]["message"])


@unittest.skipIf(agent.harness_problem(), f"agent harness: {agent.harness_problem()}")
class AgentCommandsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(runstate, "STATE", Path(self.dir.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dir.cleanup()
        progress.set_sink(None)

    def test_run_report_and_show(self):
        code, doc, err = run_cli(["agent", "run", "--json", "--repeats", "1", "--scripted",
                                  str(ROOT / "tests" / "agent_scripted.json")])
        run = doc["run"]
        try:
            self.assertEqual(code, 0)
            self.assertEqual(len(doc["rows"]), 4)
            self.assertIn(f"run {run}, scripted:", err)  # progress on standard error, not in the document
            code, report, _ = run_cli(["agent", "report", "--json", "--run", run])
            self.assertEqual(code, 0)
            self.assertEqual(report["data"]["runs"], [run])
            self.assertIn("scripted", report["data"]["models"])
            code, show, _ = run_cli(["agent", "show", "--json", run, "file-marker-1"])
            self.assertEqual(code, 0)
            self.assertEqual(show["row"]["task"], "file-marker")
            self.assertTrue(show["events"])
            code, error, _ = run_cli(["agent", "show", "--json", run, "no-such-task-1"])
            self.assertNotEqual(code, 0)
            self.assertIn("message", error["error"])
        finally:
            (ROOT / "results" / f"agent_{run}.jsonl").unlink(missing_ok=True)
            shutil.rmtree(ROOT / "results" / "agent" / run, ignore_errors=True)
            for suffix in (".md", ".json"):
                (ROOT / "report" / f"agent_{run}{suffix}").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
