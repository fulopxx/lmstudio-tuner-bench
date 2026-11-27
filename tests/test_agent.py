"""Offline tests of agent task runs: pass/fail, the failure categorizer (synthetic and recorded live traces), the
sampling profiles, the rebuild from traces and the whole path through the harness with scripted replies."""
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.cli import main as cli  # noqa: E402
from bench.core import agent, failures  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "traces"


class Trace:
    """Builds a synthetic trace with increasing sequence numbers."""

    def __init__(self, tools=("read_file", "lookup"), prompt="Where is order A-1?"):
        self.events = []
        self.add("task_start", tools=list(tools), prompt=prompt)
        self.calls = 0

    def add(self, event, **kw):
        self.events.append({"seq": len(self.events), "event": event, **kw})
        return self

    def pred(self, answer="", calls=0, stop=None, reasoning=0, text=None):
        return self.add("prediction", answer=answer, text=text if text is not None else answer, toolCalls=calls,
                        stopReason=stop or ("toolCalls" if calls else "eosFound"), reasoningChars=reasoning)

    def call(self, name, args=None, ok=True, content="", known=True, problems=(), kind=None):
        seq = self.calls
        self.calls += 1
        self.add("tool_call", parsed=True, call_seq=seq, name=name, arguments=args or {}, known=known,
                 valid=known and not problems, problems=[{"code": p} for p in problems])
        return self.add("tool_result", call_seq=seq, name=name, ok=ok, content=content, errorKind=kind)

    def end(self, status="done", answer=""):
        return self.add("task_end", status=status, answer=answer)


LOOKUP_A1 = [{"name": "lookup", "arguments": {"id": {"equals": "A-1"}}}]


def categorize(task, trace, status="done", answer=None):
    answer = answer if answer is not None else trace.events[-1].get("answer", "")
    attempt = {"status": status, "answer": answer}
    verdict = agent.evaluate_attempt(task, attempt, trace.events)
    return verdict, failures.classify(task, attempt, trace.events, verdict["passed"])


class EvaluateTest(unittest.TestCase):
    def test_pass_with_expected_calls_and_extra_call(self):
        task = {"expected_calls": LOOKUP_A1, "checks": {"answer_contains": ["shipped"]}}
        t = Trace().pred(calls=1).call("read_file", {"path": "x"}).pred(calls=1).call("lookup", {"id": "A-1"})
        t.pred("It has shipped.").end(answer="It has shipped.")
        verdict, cat = categorize(task, t)
        self.assertTrue(verdict["passed"])
        self.assertIsNone(cat["primary"])
        self.assertIn("redundant_calls", cat["flags"])

    def test_limit_fails_unless_accepted(self):
        task = {"checks": {"answer_contains": ["ok"]}}
        t = Trace().pred("ok").end(status="limit", answer="ok")
        self.assertFalse(agent.evaluate_attempt(task, {"status": "limit", "answer": "ok"}, t.events)["passed"])
        task["accept_limit"] = True
        self.assertTrue(agent.evaluate_attempt(task, {"status": "limit", "answer": "ok"}, t.events)["passed"])

    def test_deny_list_and_forbidden_and_budget(self):
        t = Trace().pred(calls=1).call("cancel", {}).pred("done").end(answer="Delivered.")
        v = agent.evaluate_attempt({"checks": {"answer_not_contains": ["delivered"]}, "forbidden_tools": ["cancel"],
                                    "max_tool_calls": 0}, {"status": "done", "answer": "Delivered."}, t.events)
        self.assertEqual(v["checks"], {"answer_not_contains": False, "forbidden_tools": False, "max_tool_calls": False})

    def test_answer_contains_any_groups(self):
        def check(value, answer):
            v = agent.evaluate_attempt({"checks": {"answer_contains_any": value}}, {"status": "done", "answer": answer},
                                       [])
            return v["checks"]["answer_contains_any"]
        self.assertTrue(check(["a", "b"], "only B"))
        groups = [["shipped", "in transit"], ["dec 1", "2026-12-01"]]
        self.assertTrue(check(groups, "In transit, arrives Dec 1"))
        self.assertFalse(check(groups, "In transit, arrives soon"))

    def test_matchers_are_type_strict(self):
        self.assertTrue(failures.arg_matches({"equals": "A-1"}, " a-1 "))
        self.assertFalse(failures.arg_matches({"equals": 3}, "3"))
        self.assertTrue(failures.arg_matches({"one_of": [1, 2]}, 2))
        self.assertTrue(failures.arg_matches({"any": True}, 0))
        self.assertFalse(failures.arg_matches({"any": True}, None))

    def test_example_tasks_are_valid(self):
        data, digest = agent.load_tasks(ROOT / "tasks" / "examples.json")
        self.assertEqual(len({t["id"] for t in data["tasks"]}), len(data["tasks"]))
        self.assertEqual(len(digest), 16)

    def test_task_file_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps({"schema_version": 2, "tasks": [
                {"id": "a", "prompt": "p", "tools": ["shell"], "expected_calls": [{"name": "x"}], "checks": {"bad": 1},
                 "oops": 1},
                {"id": "b", "prompt": "p", "checks": {"answer_contains_any": [["x"], "y"]}}]}), encoding="utf-8")
            with self.assertRaises(agent.StepError) as e:
                agent.load_tasks(p)
            for part in ("unknown key 'oops'", "unknown check 'bad'", "'shell' is not declared",
                         "expected call to 'x'", "task b: answer_contains_any must be"):
                self.assertIn(part, str(e.exception))


class CategorizerTest(unittest.TestCase):
    """One synthetic trace per category, plus priority and silent / loud."""
    task = {"expected_calls": LOOKUP_A1, "checks": {"answer_contains": ["shipped"]}}

    def primary(self, trace, task=None, status="done"):
        return categorize(task or self.task, trace, status)[1]

    def test_infra(self):
        c = self.primary(Trace().pred("x").end(status="aborted"), status="aborted")
        self.assertEqual((c["primary"], c["subcode"]), ("infra_error", "aborted"))
        c = self.primary(Trace().pred(calls=1), status="error")
        self.assertEqual(c["primary"], "infra_error")

    def test_context_overflow_and_truncation(self):
        c = self.primary(Trace().pred("", stop="contextLengthReached").end())
        self.assertEqual(c["primary"], "context_overflow")
        c = self.primary(Trace().pred("", stop="maxPredictedTokensReached", reasoning=900).end())
        self.assertEqual((c["primary"], c["subcode"]), ("output_truncated", "reasoning_exhausted"))
        self.assertFalse(c["silent"])

    def test_text_tool_call_is_format_invalid_not_no_tool(self):
        text = 'I will call it.\n```json\n{"name": "lookup", "arguments": {"id": "A-1"}}\n```'
        c = self.primary(Trace().pred(text).end(answer=text))
        self.assertEqual((c["primary"], c["subcode"]), ("format_invalid", "text_tool_call"))
        self.assertIn("no_tool_when_needed", [f["category"] for f in c["secondary"]])

    def test_xml_form_text_tool_call(self):
        text = '```xml\n<lookup id="A-1"/>\n```'
        c = self.primary(Trace().pred(text).end(answer=text))
        self.assertEqual((c["primary"], c["subcode"]), ("format_invalid", "text_tool_call"))

    def test_quoted_unknown_tool_name_is_not_a_text_call(self):
        text = '{"name": "something_else", "arguments": {}}'
        c = self.primary(Trace().pred(text).end(answer=text))
        self.assertEqual(c["primary"], "no_tool_when_needed")

    def test_sdk_parse_failure(self):
        t = Trace().add("tool_call", parsed=False, error="bad", raw="{").pred("x").end(answer="x")
        self.assertEqual(self.primary(t)["subcode"], "sdk_parse_failure")

    def test_no_tool_when_needed(self):
        c = self.primary(Trace().pred("It is probably shipped.").end(answer="It is probably shipped."))
        self.assertEqual((c["primary"], c["subcode"]), ("no_tool_when_needed", "answered_without_data"))
        self.assertTrue(c["silent"])
        c = self.primary(Trace().pred("Which order do you mean?").end(answer="Which order do you mean?"))
        self.assertEqual(c["subcode"], "asked_user")
        self.assertFalse(c["silent"])

    def test_wrong_tool(self):
        t = Trace().pred(calls=1).call("delete_all", {}, ok=False, known=False, kind="unknown_tool").pred("x").end()
        self.assertEqual(self.primary(t)["subcode"], "unknown_tool")
        t = Trace().pred(calls=1).call("read_file", {"path": "a"}).pred("It is shipped.").end(answer="It is shipped.")
        self.assertEqual((self.primary(t)["primary"], self.primary(t)["subcode"]), ("wrong_tool", "decoy"))
        task = dict(self.task, forbidden_tools=["cancel"])
        t = Trace().pred(calls=1).call("cancel", {}).pred(calls=1).call("lookup", {"id": "A-1"}).pred("shipped").end(
            answer="shipped")
        self.assertEqual(self.primary(t, task)["subcode"], "forbidden")

    def test_wrong_arguments(self):
        t = Trace().pred(calls=1).call("lookup", {"id": 1}, ok=False, problems=["wrong_type"], kind="invalid_arguments")
        t.pred("error").end(answer="error")
        self.assertEqual((self.primary(t)["primary"], self.primary(t)["subcode"]), ("wrong_arguments", "wrong_type"))
        t = Trace().pred(calls=1).call("lookup", {"id": "Z-9"}, ok=False, kind="not_found").pred("x").end(answer="x")
        self.assertEqual(self.primary(t)["subcode"], "invented_value")
        t = Trace(prompt="Order A-1 or a-2?").pred(calls=1).call("lookup", {"id": "a-2"}).pred("x").end(answer="x")
        self.assertEqual(self.primary(t)["subcode"], "wrong_value")

    def test_unnecessary_tool(self):
        task = {"no_tool_needed": True, "checks": {"answer_contains": ["42"]}}
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}).pred("42").end(answer="42")
        self.assertEqual(self.primary(t, task)["primary"], "unnecessary_tool")

    def test_loop(self):
        t = Trace()
        for _ in range(3):
            t.pred(calls=1).call("lookup", {"id": "B"}, content="pending")
        t.pred("still pending").end(answer="still pending")
        c = self.primary(t)
        self.assertEqual((c["primary"], c["subcode"]), ("wrong_arguments", "invented_value"))  # earliest evidence wins
        self.assertIn("loop", [f["category"] for f in c["secondary"]])
        task = {"expected_calls": [{"name": "lookup", "arguments": {"id": {"equals": "B"}}}],
                "checks": {"answer_contains": ["done"]}}
        c = self.primary(t, task)
        self.assertEqual((c["primary"], c["subcode"]), ("loop", "identical_calls"))
        t2 = Trace().pred(calls=1).call("lookup", {"id": "A-1"}).add("limit_hit", limit="rounds")
        t2.pred("Limit reached.").end(status="limit", answer="Limit reached.")
        c = self.primary(t2, dict(self.task, checks={"answer_contains": ["delivered"]}), status="limit")
        self.assertEqual((c["primary"], c["subcode"]), ("loop", "round_limit"))

    def test_incomplete_chain(self):
        task = {"expected_calls": LOOKUP_A1 + [{"name": "lookup", "arguments": {"id": {"equals": "C-3"}}}],
                "checks": {"answer_contains": ["C-3 shipped"]}}
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}, content="next: C-3").pred("A-1 is fine.")
        t.end(answer="A-1 is fine.")
        self.assertEqual(self.primary(t, task)["primary"], "incomplete_chain")

    def test_limit_silent(self):
        task = {"expected_calls": LOOKUP_A1, "accept_limit": True, "checks": {"answer_contains": ["delivered"]}}
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}, ok=False, kind="timeout").add("limit_hit",
                                                                                              limit="tool_timeout")
        t.pred("It is shipped.").end(answer="It is shipped.")
        c = self.primary(t, task)
        self.assertEqual((c["primary"], c["subcode"]), ("limit_silent", "tool_timeout"))
        self.assertTrue(c["silent"])

    def test_ignored_tool_error(self):
        task = {"expected_calls": LOOKUP_A1, "checks": {"mentions_failure": ["unavailable"],
                                                        "answer_not_contains": ["shipped"]}}
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}, ok=False, kind="mock_error")
        t.pred("It has shipped.").end(answer="It has shipped.")
        c = self.primary(t, task)
        self.assertEqual((c["primary"], c["subcode"]), ("ignored_tool_error", "fabricated"))
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}, ok=False, kind="mock_error")
        t.pred("All good.").end(answer="All good.")
        self.assertEqual(self.primary(t, task)["subcode"], "not_reported")

    def test_wrong_result(self):
        task = {"expected_calls": LOOKUP_A1, "checks": {"answer_contains": ["shipped", "DHL"]}}
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}).pred("It shipped.").end(answer="It shipped.")
        self.assertEqual(self.primary(t, task)["subcode"], "partial")
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}).pred("").end(answer="")
        self.assertEqual(self.primary(t, task)["subcode"], "empty_answer")
        t = Trace().pred(calls=1).call("lookup", {"id": "A-1"}, ok=False, kind="mock_error")
        t.pred("The service is unavailable, please try later.").end(answer="The service is unavailable, please try later.")
        c = self.primary(t, task)
        self.assertEqual((c["primary"], c["subcode"]), ("wrong_result", "gave_up"))
        self.assertFalse(c["silent"])

    def test_unclassified(self):
        task = {"checks": {"answer_contains": ["x"]}}  # no expected calls: the steps cannot be judged
        c = self.primary(Trace().pred("y").end(answer="y"), task)
        self.assertEqual(c["primary"], "unclassified")
        task = {"no_tool_needed": True, "checks": {"answer_contains": ["42"]}}
        c = self.primary(Trace().pred("41").end(answer="41"), task)
        self.assertEqual((c["primary"], c["subcode"]), ("wrong_result", "wrong_value"))

    def test_flags(self):
        task = {"expected_calls": LOOKUP_A1, "checks": {"answer_contains": ["shipped"]}}
        t = Trace().pred(calls=2).call("read_file", {"path": "../x"}, ok=False, kind="outside_sandbox")
        t.call("lookup", {"id": "A-1"}).pred("shipped <think>").end(answer="shipped <think>")
        verdict, c = categorize(task, t)
        self.assertTrue(verdict["passed"])
        self.assertEqual(set(c["flags"]), {"recovered_error", "redundant_calls", "parallel_calls", "reasoning_leak",
                                           "sandbox_escape_attempt"})

    def test_every_category_has_a_test_and_a_document_entry(self):
        source = Path(__file__).read_text(encoding="utf-8")
        for cat in failures.CATEGORIES:
            self.assertIn(f'"{cat}"', source, f"no test mentions {cat}")
        for doc in ("failure_taxonomy.md", "failure_taxonomy.hu.md"):
            text = (ROOT / "docs" / doc).read_text(encoding="utf-8")
            for name in list(failures.CATEGORIES) + failures.FLAGS:
                self.assertIn(f"`{name}`", text, f"{doc} does not describe {name}")
            for info in failures.CATEGORIES.values():
                for sub in info["subcodes"]:
                    self.assertIn(f"`{sub}`", text, f"{doc} does not describe subcode {sub}")


class RecordedTraceTest(unittest.TestCase):
    """Live traces (2026-11-26) as regression samples."""

    def test_text_tool_call_of_a_coder_model(self):
        events = agent.read_events(FIXTURES / "live_text_tool_call.jsonl")
        task = {"expected_calls": [{"name": "mock_lookup", "arguments": {"order_id": {"equals": "A-1042"}}}],
                "checks": {"answer_contains": ["shipped"]}}
        attempt = {"status": "done", "answer": events[-1]["answer"]}
        verdict = agent.evaluate_attempt(task, attempt, events)
        c = failures.classify(task, attempt, events, verdict["passed"])
        self.assertEqual((c["primary"], c["subcode"]), ("format_invalid", "text_tool_call"))

    def test_reported_timeout_of_a_thinking_model_passes(self):
        events = agent.read_events(FIXTURES / "live_timeout_reported.jsonl")
        task = {"expected_calls": [{"name": "mock_lookup", "arguments": {"order_id": {"equals": "C-55"}}}],
                "checks": {"mentions_failure": ["unable", "didn't respond", "try again"],
                           "answer_not_contains": ["delivered"]}}
        attempt = {"status": "done", "answer": events[-1]["answer"]}
        verdict = agent.evaluate_attempt(task, attempt, events)
        self.assertTrue(verdict["passed"], verdict)
        self.assertIn("recovered_error", failures.classify(task, attempt, events, True)["flags"])


class SamplingTest(unittest.TestCase):
    def test_profiles(self):
        s = agent.sampling_for("qwen3-8b")
        self.assertEqual((s["temperature"], s["topP"], s["topK"]), (0.6, 0.95, 20))
        self.assertEqual(agent.sampling_for("qwen2.5-coder-7b-instruct")["repeatPenalty"], 1.1)
        self.assertEqual(agent.sampling_for("qwen3.5-4b-mtp")["topK"], 20)
        self.assertTrue(agent.sampling_for("llama-3.2-1b-instruct")["source"].startswith("fallback"))
        o = agent.sampling_for("qwen3-8b", 0.0)
        self.assertEqual((o["temperature"], o["topP"]), (0.0, 0.95))
        self.assertIn("overridden", o["source"])


class RebuildTest(unittest.TestCase):
    def test_attempts_from_traces(self):
        with tempfile.TemporaryDirectory() as d:
            traces = Path(d) / "traces"
            traces.mkdir()
            (traces / "a-1.jsonl").write_text(json.dumps({"seq": 0, "event": "task_start"}) + "\n" + json.dumps(
                {"seq": 1, "event": "task_end", "status": "done", "answer": "ok", "rounds": 1}) + "\n", encoding="utf-8")
            (traces / "a-2.jsonl").write_text(json.dumps({"seq": 0, "event": "task_start"}) + "\n{broken",
                                              encoding="utf-8")
            rows = agent.attempts_from_traces(d, [{"id": "a"}], 3)
        self.assertEqual([r["status"] for r in rows], ["done", "error", "skipped"])
        self.assertEqual(rows[0]["answer"], "ok")


@unittest.skipIf(agent.harness_problem(), f"agent harness: {agent.harness_problem()}")
class ScriptedRunTest(unittest.TestCase):
    def test_example_tasks_through_the_harness(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["agent", "run", "--repeats", "1", "--scripted", str(ROOT / "tests" / "agent_scripted.json")])
        self.assertEqual(code, 0, out.getvalue())
        text = out.getvalue()
        results = Path(next(ln for ln in text.splitlines() if ln.startswith("results: "))[len("results: "):])
        try:
            rows = {r["task"]: r for r in map(json.loads, results.read_text(encoding="utf-8").splitlines())}
            self.assertTrue(rows["file-marker"]["passed"])
            self.assertTrue(rows["order-status"]["passed"])
            self.assertFalse(rows["tool-error"]["passed"])  # the scripted reply never calls the tool
            self.assertEqual((rows["tool-error"]["primary"], rows["tool-error"]["subcode"]),
                             ("no_tool_when_needed", "answered_without_data"))
            self.assertTrue(rows["tool-error"]["silent"])
            self.assertTrue(rows["tool-timeout"]["passed"])
            self.assertEqual(rows["tool-timeout"]["limits_hit"], ["tool_timeout"])
            self.assertTrue(all(r["trace_complete"] for r in rows.values()))
            self.assertTrue(re.search(r"passed 3/4", text))
            first = agent.read_events(rows["file-marker"]["trace"])[0]
            self.assertEqual(first["schema_version"], 2)
            self.assertEqual(first["model"], "scripted")
            self.assertTrue(first["taskFileHash"])
        finally:
            results.unlink(missing_ok=True)
            shutil.rmtree(ROOT / "results" / "agent" / results.stem[len("agent_"):], ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
