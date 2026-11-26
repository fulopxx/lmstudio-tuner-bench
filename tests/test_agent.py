"""Offline tests of agent task runs: checks, and the whole path through the harness with scripted replies."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runner"))
import agent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class EvaluateTest(unittest.TestCase):
    task = {"checks": {"tool_called": "read_file", "answer_contains": ["BLUE-HERON-17"]}}
    events = [{"event": "tool_call", "parsed": True, "name": "read_file"}, {"event": "task_end"}]

    def test_pass(self):
        v = agent.evaluate_attempt(self.task, {"status": "done", "answer": "It is blue-heron-17."}, self.events)
        self.assertTrue(v["passed"])
        self.assertTrue(v["trace_complete"])

    def test_wrong_answer_or_status_fails(self):
        self.assertFalse(agent.evaluate_attempt(self.task, {"status": "done", "answer": "no idea"}, self.events)["passed"])
        self.assertFalse(agent.evaluate_attempt(self.task, {"status": "aborted", "answer": "BLUE-HERON-17"},
                                                self.events)["passed"])

    def test_unparsed_call_does_not_count(self):
        events = [{"event": "tool_call", "parsed": False, "raw": "{"}]
        v = agent.evaluate_attempt(self.task, {"status": "done", "answer": "BLUE-HERON-17"}, events)
        self.assertEqual(v["checks"]["tool_called"], False)
        self.assertFalse(v["trace_complete"])

    def test_tool_not_called_star(self):
        task = {"checks": {"tool_not_called": "*"}}
        self.assertTrue(agent.evaluate_attempt(task, {"status": "done", "answer": "42"}, [])["passed"])
        self.assertFalse(agent.evaluate_attempt(task, {"status": "done", "answer": "42"}, self.events)["passed"])

    def test_broken_trace_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text('{"event": "task_start"}\n{"event": "tool_ca', encoding="utf-8")
            self.assertEqual(agent.read_events(p), [{"event": "task_start"}])

    def test_example_tasks_are_valid(self):
        data = agent.load_tasks(ROOT / "tasks" / "examples.json")
        self.assertEqual(len({t["id"] for t in data["tasks"]}), len(data["tasks"]))


class ScriptedRunTest(unittest.TestCase):
    def test_example_tasks_through_the_harness(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = agent.main(["run", "--scripted", str(ROOT / "tests" / "agent_scripted.json")])
        self.assertEqual(code, 0, out.getvalue())
        text = out.getvalue()
        results = Path(next(ln for ln in text.splitlines() if ln.startswith("results: "))[len("results: "):])
        try:
            rows = {r["task"]: r for r in map(json.loads, results.read_text(encoding="utf-8").splitlines())}
            self.assertTrue(rows["file-marker"]["passed"])
            self.assertTrue(rows["order-status"]["passed"])
            self.assertFalse(rows["tool-error"]["passed"])  # the scripted reply never calls the tool
            self.assertEqual(rows["tool-error"]["checks"]["tool_called"], False)
            self.assertTrue(rows["tool-timeout"]["passed"])
            self.assertEqual(rows["tool-timeout"]["limits_hit"], ["tool_timeout"])
            self.assertTrue(all(r["trace_complete"] for r in rows.values()))
            self.assertIn("passed 3/4", text)
        finally:
            results.unlink(missing_ok=True)
            shutil.rmtree(ROOT / "results" / "agent" / results.stem[len("agent_"):], ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
