"""Offline tests of the M1 task set, the report and the multi-model run (FA-08, FA-39 to FA-47)."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import agent, agent_report, failures, runstate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_REAL_STATE = runstate.STATE


def setUpModule():  # runs write their run state into a temporary folder, never into the real state/
    global _state
    _state = tempfile.TemporaryDirectory()
    runstate.STATE = Path(_state.name)


def tearDownModule():
    runstate.STATE = _REAL_STATE
    _state.cleanup()
TASKS = ROOT / "tasks" / "m1.json"
REFERENCE = ROOT / "tests" / "m1_reference.json"
FAILURES = ROOT / "tests" / "m1_failures.json"


def run_scripted(replies_file, extra=()):
    """Runs the M1 task set with scripted replies; returns the result rows, the run id and the output."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["agent", "run", "--tasks", str(TASKS), "--repeats", "1", "--scripted", str(replies_file), *extra])
    text = out.getvalue()
    assert code == 0, text
    path = Path(next(ln for ln in text.splitlines() if ln.startswith("results: "))[len("results: "):])
    run_id = path.stem[len("agent_"):]
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return rows, run_id, text


def cleanup(run_id):
    (ROOT / "results" / f"agent_{run_id}.jsonl").unlink(missing_ok=True)
    shutil.rmtree(ROOT / "results" / "agent" / run_id, ignore_errors=True)
    for suffix in (".md", ".json"):
        (ROOT / "report" / f"agent_{run_id}{suffix}").unlink(missing_ok=True)


class TaskSetTest(unittest.TestCase):
    def test_twenty_tasks_with_reference_and_failure(self):
        data, _ = agent.load_tasks(TASKS)
        ids = [t["id"] for t in data["tasks"]]
        self.assertEqual(len(ids), 20)
        self.assertEqual(set(json.loads(REFERENCE.read_text(encoding="utf-8"))), set(ids))
        f = json.loads(FAILURES.read_text(encoding="utf-8"))
        self.assertEqual(set(f["expected"]), set(ids))
        self.assertEqual(set(f["replies"]), set(ids))
        for expected in f["expected"].values():
            cat, _, sub = expected.partition("/")
            self.assertIn(cat, failures.CATEGORIES)
            if sub:
                self.assertIn(sub, failures.CATEGORIES[cat]["subcodes"])

    def test_chain_lengths_two_tasks_each_above_two(self):
        data, _ = agent.load_tasks(TASKS)
        lengths = [t.get("chain_length") for t in data["tasks"] if t.get("chain_length")]
        self.assertEqual(sorted(lengths), [1, 1, 2, 3, 3, 4, 4])
        for t in data["tasks"]:
            if t.get("chain_length", 0) > 1:
                self.assertEqual(len(t["expected_calls"]), t["chain_length"], t["id"])

    def test_answer_tokens_are_not_in_the_prompt(self):
        """FA-05: the facts a correct answer needs come from tools, not from the prompt (except none-in-prompt)."""
        data, _ = agent.load_tasks(TASKS)
        for t in data["tasks"]:
            if t["id"] == "none-in-prompt":
                continue
            for token in t.get("checks", {}).get("answer_contains", []):
                self.assertNotIn(token.lower(), t["prompt"].lower(), t["id"])


@unittest.skipIf(agent.harness_problem(), f"agent harness: {agent.harness_problem()}")
class ScriptedM1Test(unittest.TestCase):
    def test_reference_solutions_pass(self):
        rows, run_id, _ = run_scripted(REFERENCE)
        try:
            failed = [(r["task"], r["primary"], r["checks"]) for r in rows if not r["passed"]]
            self.assertEqual(failed, [])
        finally:
            cleanup(run_id)

    def test_failing_replies_get_the_expected_category(self):
        f = json.loads(FAILURES.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            replies = Path(d) / "replies.json"
            replies.write_text(json.dumps(f["replies"]), encoding="utf-8")
            rows, run_id, _ = run_scripted(replies)
        try:
            got = {r["task"]: r["primary"] + (f"/{r['subcode']}" if r["subcode"] else "") for r in rows
                   if not r["passed"]}
            self.assertEqual(got, f["expected"])
            # report and show on the same run (FA-43, FA-47)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["agent", "report", "--run", run_id, "--k", "1", "--tasks", str(TASKS)]), 0)
                self.assertEqual(cli.main(["agent", "show", run_id, "chain-3b-1"]), 0)
            text = out.getvalue()
            self.assertIn("| scripted | 20 | 0 |", text)
            self.assertIn("re-judged with", text)
            self.assertRegex(text, r">>\s+5 tool_call\s+call #1 get_order_status")
            report = json.loads((ROOT / "report" / f"agent_{run_id}.json").read_text(encoding="utf-8"))
            model = report["models"]["scripted"]
            self.assertEqual(model["categories"]["unnecessary_tool"], 3)
            self.assertIn("unnecessary_tool", model["mitigations"])
        finally:
            cleanup(run_id)


class ReportTest(unittest.TestCase):
    def test_wilson(self):
        lo, hi = agent_report.wilson(5, 5)
        self.assertAlmostEqual(lo, 0.566, places=2)
        self.assertEqual(hi, 1.0)
        lo, hi = agent_report.wilson(8, 10)
        self.assertAlmostEqual(lo, 0.49, places=2)
        self.assertAlmostEqual(hi, 0.94, places=2)
        self.assertEqual(agent_report.wilson(0, 0), (None, None))

    def test_pass_hat_k(self):
        self.assertAlmostEqual(agent_report.pass_hat_k([(4, 5)], 2), 6 / 10)
        self.assertEqual(agent_report.pass_hat_k([(5, 5), (0, 5)], 5), 0.5)
        self.assertIsNone(agent_report.pass_hat_k([(1, 2)], 3))

    def test_longest_chain_needs_every_shorter_length(self):
        tasks = {"a": {"chain_length": 1}, "b": {"chain_length": 2}, "c": {"chain_length": 3}, "d": {"chain_length": 4}}
        per_task = {"a": (10, 10), "b": (9, 10), "c": (5, 10), "d": (10, 10)}
        chain = agent_report.longest_chain(per_task, tasks, 0.8)
        self.assertEqual(chain["length"], 2)
        self.assertTrue(chain["per_length"][4]["reliable"])  # reliable alone, but length 3 is not

    def test_format_stuck_note_and_infra_exclusion(self):
        rows = [{"model": "m", "task": f"t{i}", "attempt": 1, "passed": False, "primary": "format_invalid",
                 "subcode": "text_tool_call", "secondary": [], "flags": [], "silent": False, "rounds": 1,
                 "seconds": 1, "evidence": {"seq": 1, "rule": "r"}} for i in range(4)]
        rows.append({"model": "m", "task": "*", "attempt": 0, "passed": False, "primary": "infra_error"})
        s = agent_report.summarize(rows, {}, k=1)["m"]
        self.assertEqual((s["attempts"], s["infra"]), (4, 1))
        self.assertTrue(any("FA-39" in n for n in s["notes"]))
        self.assertIn("format_invalid", s["mitigations"])


class MultiModelTest(unittest.TestCase):
    def test_computed_time_limit(self):
        data, _ = agent.load_tasks(TASKS)
        a = mock.Mock(run_timeout=None, repeats=2)
        expected = 2 * sum(t.get("limits", {}).get("wallTimeMs", 180_000) / 1000 + 5 for t in data["tasks"]) + 120
        self.assertEqual(agent.run_timeout(a, data, data["tasks"]), int(expected))
        self.assertEqual(agent.run_timeout(mock.Mock(run_timeout=99), data, data["tasks"]), 99)

    def test_a_failing_model_is_recorded_and_the_next_one_runs(self):
        calls = []

        def fake_run_model(a, model, *rest):
            calls.append(model)
            if model == "bad":
                raise agent.StepError("fail", "load failed")
            return [], {"attempts": [], "stopped": False}, {"model": model}

        out = io.StringIO()
        with mock.patch.object(agent, "run_model", fake_run_model), \
                mock.patch.object(agent, "harness_problem", lambda: None), redirect_stdout(out):
            code = cli.main(["agent", "run", "--tasks", str(TASKS), "--models", "bad,good"])
        text = out.getvalue()
        run_id = next(ln for ln in text.splitlines() if ln.startswith("results: ")).rsplit("agent_", 1)[1][:-6]
        try:
            self.assertEqual(code, 0)
            self.assertEqual(calls, ["bad", "good"])
            rows = [json.loads(line) for line in
                    (ROOT / "results" / f"agent_{run_id}.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([(r["model"], r["task"], r["primary"]) for r in rows], [("bad", "*", "infra_error")])
        finally:
            cleanup(run_id)

    def test_no_further_model_starts_after_the_user_stopped_the_run(self):
        calls = []

        def fake_run_model(a, model, *rest):
            calls.append(model)
            agent.USER_STOP.set()  # as run_harness does on Ctrl+C
            return [], {"attempts": [], "stopped": True}, {"model": model}

        out = io.StringIO()
        with mock.patch.object(agent, "run_model", fake_run_model),                 mock.patch.object(agent, "harness_problem", lambda: None), redirect_stdout(out):
            code = cli.main(["agent", "run", "--tasks", str(TASKS), "--models", "first,second"])
        run_id = next(ln for ln in out.getvalue().splitlines() if ln.startswith("results: ")).rsplit("agent_", 1)[1][:-6]
        try:
            self.assertEqual(code, 0)
            self.assertEqual(calls, ["first"])
            self.assertIn("1 model(s) not started", out.getvalue())
            self.assertEqual(runstate.read_status(run_id)["state"], "stopped")
        finally:
            cleanup(run_id)


@unittest.skipIf(agent.harness_problem(), f"agent harness: {agent.harness_problem()}")
class CoreIsSilentTest(unittest.TestCase):
    """CR-03: core functions print nothing; progress lines go only to the progress sink."""

    def test_core_functions_print_nothing(self):
        from bench.core import progress, sweep
        options = cli.agent_parser().parse_args(
            ["run", "--tasks", str(TASKS), "--only", "direct-file", "--repeats", "1", "--scripted", str(REFERENCE)])
        lines = []
        out = io.StringIO()
        try:
            progress.set_sink(lines.append)
            with redirect_stdout(out):
                result = agent.run_tasks(options)
                agent.report([result["run"]], None, 1, 0.8)
                agent.show_attempt(result["run"], "direct-file-1")
                sweep.run_status()
        finally:
            progress.set_sink(None)
            cleanup(result["run"])
        self.assertEqual(out.getvalue(), "")
        self.assertTrue(any(line.startswith(f"run {result['run']}") for line in lines))


if __name__ == "__main__":
    unittest.main()
