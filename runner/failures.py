"""Failure taxonomy and the rule-based categorizer of agent attempts (FA-30 to FA-39).

The categorizer reads one attempt's trace events and the task definition and returns one primary category with a
subcode, the evidence (event sequence number and rule name), further findings and flags. Levels (FA-31):

  structural   fixed order: infra_error > context_overflow > output_truncated > format_invalid
  behavioural  the finding whose first evidence comes earliest in the trace wins; ties in the order of BEHAVIOURAL
  outcome      fixed order, only when there is no behavioural finding

CATEGORIES is the single machine-readable source of the taxonomy (FA-38); docs/failure_taxonomy.md and its Hungarian
version describe each id. Pure functions only: no I/O, so the rules can be tested on synthetic and recorded traces.
"""
import json
import re

TAXONOMY_VERSION = 1

# id -> level, reliability ("rule": decided by structure; "heuristic": depends on text matching), subcodes
CATEGORIES = {
    "infra_error": {"level": "structural", "reliability": "rule",
                    "subcodes": ["harness_error", "aborted", "skipped", "incomplete_trace"]},
    "context_overflow": {"level": "structural", "reliability": "rule", "subcodes": []},
    "output_truncated": {"level": "structural", "reliability": "rule", "subcodes": ["reasoning_exhausted", "max_tokens"]},
    "format_invalid": {"level": "structural", "reliability": "heuristic",
                       "subcodes": ["sdk_parse_failure", "text_tool_call"]},
    "no_tool_when_needed": {"level": "behavioural", "reliability": "rule",
                            "subcodes": ["asked_user", "answered_without_data"]},
    "wrong_tool": {"level": "behavioural", "reliability": "rule", "subcodes": ["unknown_tool", "decoy", "forbidden"]},
    "wrong_arguments": {"level": "behavioural", "reliability": "rule",
                        "subcodes": ["missing_required", "wrong_type", "wrong_value", "invented_value"]},
    "unnecessary_tool": {"level": "behavioural", "reliability": "rule", "subcodes": []},
    "loop": {"level": "behavioural", "reliability": "rule", "subcodes": ["identical_calls", "round_limit"]},
    "incomplete_chain": {"level": "behavioural", "reliability": "rule", "subcodes": []},
    "limit_silent": {"level": "outcome", "reliability": "heuristic", "subcodes": ["rounds", "wall_time", "tool_timeout"]},
    "ignored_tool_error": {"level": "outcome", "reliability": "heuristic", "subcodes": ["fabricated", "not_reported"]},
    "wrong_result": {"level": "outcome", "reliability": "rule", "subcodes": ["empty_answer", "partial", "wrong_value"]},
    "unclassified": {"level": "outcome", "reliability": "rule", "subcodes": []},
}
FLAGS = ["recovered_error", "redundant_calls", "parallel_calls", "reasoning_leak", "sandbox_escape_attempt"]
STRUCTURAL = ["infra_error", "context_overflow", "output_truncated", "format_invalid"]
BEHAVIOURAL = ["no_tool_when_needed", "wrong_tool", "wrong_arguments", "unnecessary_tool", "loop", "incomplete_chain"]
OUTCOME = ["limit_silent", "ignored_tool_error", "wrong_result", "unclassified"]

# words by which an answer tells the user that something went wrong (heuristic; used for "silent" and the outcome level)
PROBLEM_SIGNALS = ["error", "fail", "unable", "could not", "couldn't", "cannot", "can't", "not available",
                   "unavailable", "timed out", "timeout", "time out", "did not answer", "didn't respond", "not respond",
                   "limit", "incomplete", "not found", "try again", "unfortunately", "sorry"]
LEAK_MARKERS = ["<think>", "</think>", "__LM_STUDIO_INTERNAL"]
DEFAULT_LOOP_THRESHOLD = 3


# ---------------------------------------------------------------- matching helpers (shared with the pass/fail check)

def canon(value):
    """Canonical form for comparisons: strings trimmed and lower-cased, everything else as JSON."""
    if isinstance(value, str):
        return value.strip().lower()
    return json.dumps(value, sort_keys=True)


def arg_matches(matcher, value):
    if "any" in matcher:
        return value is not None
    if "equals" in matcher:
        return value is not None and type(value) is type(matcher["equals"]) and canon(value) == canon(matcher["equals"])
    if "one_of" in matcher:
        return any(value is not None and type(value) is type(x) and canon(value) == canon(x) for x in matcher["one_of"])
    raise ValueError(f"unknown matcher {matcher}")


def call_matches(expected, call):
    return call.get("name") == expected["name"] and all(
        arg_matches(m, (call.get("arguments") or {}).get(k)) for k, m in expected.get("arguments", {}).items())


def subsequence_prefix(expected_calls, calls):
    """Length of the longest prefix of expected_calls found in order in calls (extra calls allowed, FA-04),
    and the call_seq of each matched call."""
    i, seqs = 0, []
    for c in calls:
        if i < len(expected_calls) and call_matches(expected_calls[i], c):
            seqs.append(c.get("call_seq"))
            i += 1
    return i, seqs


def contains_any(text, words):
    t = (text or "").lower()
    return any(w.lower() in t for w in words)


# ---------------------------------------------------------------- event views

def _events(events, kind):
    return [e for e in events if e.get("event") == kind]


def parsed_calls(events):
    return [e for e in _events(events, "tool_call") if e.get("parsed")]


def _final_answer(events, attempt):
    if attempt and attempt.get("answer") is not None:
        return attempt.get("answer") or ""
    end = _events(events, "task_end")
    return (end[-1].get("answer") if end else "") or ""


def _offered_tools(events):
    start = _events(events, "task_start")
    return start[0].get("tools", []) if start else []


def _text_tool_call(pred, tools):
    """A tool call written as text: an offered tool's name in a call form (JSON name field, <tool_call>, <function=)."""
    text = pred.get("answer") or pred.get("text") or ""
    for name in tools:
        n = re.escape(name)
        if re.search(r'"name"\s*:\s*"' + n + '"', text) or re.search(r"<function=" + n + r"\b", text):
            return name
    if "<tool_call>" in text:
        return "<tool_call>"
    return None


def _finding(category, subcode, seq, rule):
    return {"category": category, "subcode": subcode, "seq": seq, "rule": rule}


# ---------------------------------------------------------------- detectors: each returns a finding or None

def _infra(task, attempt, events):
    status = (attempt or {}).get("status")
    if status == "skipped":
        return _finding("infra_error", "skipped", None, "status_skipped")
    if status == "aborted":
        return _finding("infra_error", "aborted", None, "status_aborted")
    errors = _events(events, "error")
    if status == "error" or errors:
        return _finding("infra_error", "harness_error", errors[0].get("seq") if errors else None, "harness_error")
    if not events or events[-1].get("event") != "task_end":
        return _finding("infra_error", "incomplete_trace", events[-1].get("seq") if events else None, "no_task_end")
    return None


def _context_overflow(task, attempt, events):
    for p in _events(events, "prediction"):
        if p.get("stopReason") == "contextLengthReached":
            return _finding("context_overflow", None, p.get("seq"), "stop_reason_context_length")
    return None


def _output_truncated(task, attempt, events):
    for p in _events(events, "prediction"):
        if p.get("stopReason") == "maxPredictedTokensReached":
            sub = "reasoning_exhausted" if not (p.get("answer") or "").strip() and p.get("reasoningChars") else "max_tokens"
            return _finding("output_truncated", sub, p.get("seq"), "stop_reason_max_tokens")
    return None


def _format_invalid(task, attempt, events):
    for c in _events(events, "tool_call"):
        if not c.get("parsed"):
            return _finding("format_invalid", "sdk_parse_failure", c.get("seq"), "sdk_reported_failure")
    tools = _offered_tools(events)
    for p in _events(events, "prediction"):
        if not p.get("toolCalls") and _text_tool_call(p, tools):
            return _finding("format_invalid", "text_tool_call", p.get("seq"), "tool_call_written_as_text")
    return None


def _no_tool_when_needed(task, attempt, events):
    if not task.get("expected_calls") or parsed_calls(events):
        return None
    preds = _events(events, "prediction")
    seq = preds[0].get("seq") if preds else None
    answer = _final_answer(events, attempt).strip()
    sub = "asked_user" if answer.endswith("?") else "answered_without_data"
    return _finding("no_tool_when_needed", sub, seq, "no_call_although_expected")


def _wrong_tool(task, attempt, events):
    forbidden = set(task.get("forbidden_tools", []))
    expected = task.get("expected_calls") or []
    expected_names = {e["name"] for e in expected}
    calls = parsed_calls(events)
    done, _ = subsequence_prefix(expected, calls)
    for c in calls:
        if c.get("known") is False:
            return _finding("wrong_tool", "unknown_tool", c.get("seq"), "call_to_unknown_tool")
        if c.get("name") in forbidden:
            return _finding("wrong_tool", "forbidden", c.get("seq"), "call_to_forbidden_tool")
    if expected and done < len(expected):
        for c in calls:
            if c.get("name") not in expected_names:
                return _finding("wrong_tool", "decoy", c.get("seq"), "unexpected_tool_and_chain_not_done")
    return None


def _known_values(events, task, before_seq):
    """Text the model could have taken values from before a call: the prompt and earlier tool results."""
    parts = [task.get("prompt", "")]
    start = _events(events, "task_start")
    if start:
        parts.append(start[0].get("prompt", ""))
    parts += [r.get("content", "") for r in _events(events, "tool_result") if (r.get("seq") or 0) < before_seq]
    return "\n".join(parts).lower()


def _wrong_arguments(task, attempt, events):
    calls = parsed_calls(events)
    for c in calls:
        if c.get("known") and c.get("valid") is False:
            codes = [p.get("code") for p in c.get("problems", [])]
            sub = ("missing_required" if "missing_required" in codes else
                   "wrong_type" if "wrong_type" in codes else "wrong_value")
            return _finding("wrong_arguments", sub, c.get("seq"), "schema_check_failed")
    expected = task.get("expected_calls") or []
    done, matched = subsequence_prefix(expected, calls)
    if done < len(expected):
        nxt = expected[done]
        after = matched[-1] if matched else -1  # only calls after the last matched one can be meant for the next step
        for c in calls:
            if (c.get("call_seq") if c.get("call_seq") is not None else -1) <= after and matched:
                continue
            if c.get("name") == nxt["name"] and not call_matches(nxt, c):
                values = [v for v in (c.get("arguments") or {}).values() if isinstance(v, str)]
                known = _known_values(events, task, c.get("seq") or 0)
                invented = [v for v in values if v.strip() and v.strip().lower() not in known]
                sub = "invented_value" if invented else "wrong_value"
                return _finding("wrong_arguments", sub, c.get("seq"), "expected_arguments_not_matched")
    return None


def _unnecessary_tool(task, attempt, events):
    if not task.get("no_tool_needed"):
        return None
    calls = parsed_calls(events)
    return _finding("unnecessary_tool", None, calls[0].get("seq"), "call_although_none_needed") if calls else None


def _loop(task, attempt, events):
    n = task.get("loop_threshold", DEFAULT_LOOP_THRESHOLD)
    seen = {}
    for c in parsed_calls(events):
        key = (c.get("name"), json.dumps(c.get("arguments"), sort_keys=True))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= n:
            return _finding("loop", "identical_calls", c.get("seq"), f"same_call_{n}_times")
    if task.get("accept_limit"):
        return None
    for h in _events(events, "limit_hit"):
        if h.get("limit") == "rounds":
            return _finding("loop", "round_limit", h.get("seq"), "round_limit_hit")
    return None


def _incomplete_chain(task, attempt, events):
    expected = task.get("expected_calls") or []
    calls = parsed_calls(events)
    done, _ = subsequence_prefix(expected, calls)
    if not (0 < done < len(expected)):
        return None
    preds = _events(events, "prediction")
    if preds and not preds[-1].get("toolCalls"):
        return _finding("incomplete_chain", None, preds[-1].get("seq"), "stopped_before_chain_end")
    return None


def _failure_words(task):
    return task.get("checks", {}).get("mentions_failure") or PROBLEM_SIGNALS


def _limit_silent(task, attempt, events):
    answer = _final_answer(events, attempt)
    for h in _events(events, "limit_hit"):
        if not contains_any(answer, _failure_words(task)):
            return _finding("limit_silent", h.get("limit"), h.get("seq"), "limit_hit_not_reported")
    return None


def _ignored_tool_error(task, attempt, events):
    answer = _final_answer(events, attempt)
    failed = [r for r in _events(events, "tool_result") if r.get("ok") is False]
    if not failed:
        return None
    deny = task.get("checks", {}).get("answer_not_contains", [])
    if deny and contains_any(answer, deny):
        return _finding("ignored_tool_error", "fabricated", failed[0].get("seq"), "denied_value_in_answer")
    if not contains_any(answer, _failure_words(task)):
        return _finding("ignored_tool_error", "not_reported", failed[0].get("seq"), "tool_error_not_reported")
    return None


def _wrong_result(task, attempt, events):
    """Only when the steps were right: the expected calls were made, or the task needs no tool and none was called."""
    expected = task.get("expected_calls") or []
    calls = parsed_calls(events)
    if expected:
        if subsequence_prefix(expected, calls)[0] < len(expected):
            return None
    elif not (task.get("no_tool_needed") and not calls):
        return None
    answer = _final_answer(events, attempt)
    end = _events(events, "task_end")
    seq = end[-1].get("seq") if end else None
    if not answer.strip():
        return _finding("wrong_result", "empty_answer", seq, "empty_answer")
    wanted = task.get("checks", {}).get("answer_contains", [])
    if wanted and 0 < sum(w.lower() in answer.lower() for w in wanted) < len(wanted):
        return _finding("wrong_result", "partial", seq, "some_expected_facts_missing")
    return _finding("wrong_result", "wrong_value", seq, "answer_checks_failed")


STRUCTURAL_DETECTORS = [_infra, _context_overflow, _output_truncated, _format_invalid]
BEHAVIOURAL_DETECTORS = [_no_tool_when_needed, _wrong_tool, _wrong_arguments, _unnecessary_tool, _loop,
                         _incomplete_chain]
OUTCOME_DETECTORS = [_limit_silent, _ignored_tool_error, _wrong_result]


# ---------------------------------------------------------------- flags and the silent / loud class

def flags(task, attempt, events, passed):
    out = []
    calls = parsed_calls(events)
    results = _events(events, "tool_result")
    if passed and (any(r.get("ok") is False for r in results) or any(c.get("valid") is False for c in calls)):
        out.append("recovered_error")
    keys = [(c.get("name"), json.dumps(c.get("arguments"), sort_keys=True)) for c in calls]
    if len(keys) != len(set(keys)) or len(calls) > len(task.get("expected_calls") or []) > 0:
        out.append("redundant_calls")
    if any((p.get("toolCalls") or 0) > 1 for p in _events(events, "prediction")):
        out.append("parallel_calls")
    if contains_any(_final_answer(events, attempt), LEAK_MARKERS):
        out.append("reasoning_leak")
    if any(r.get("errorKind") == "outside_sandbox" for r in results):
        out.append("sandbox_escape_attempt")
    return out


def is_silent(primary, events, attempt):
    """A failure the user cannot notice (FA-35): the run ended normally, the answer is not empty and gives no sign of
    a problem. Heuristic, by PROBLEM_SIGNALS."""
    if primary["category"] in STRUCTURAL:
        return False
    answer = _final_answer(events, attempt)
    return bool(answer.strip()) and not answer.strip().endswith("?") and not contains_any(answer, PROBLEM_SIGNALS)


# ---------------------------------------------------------------- the categorizer

def classify(task, attempt, events, passed):
    """Primary category, subcode, evidence, secondary findings and flags of one attempt (FA-30 to FA-36).
    `task` is the task as written in the task file, `attempt` the harness summary of the attempt (status, answer),
    `events` the parsed trace, `passed` the pass/fail verdict."""
    result = {"taxonomy_version": TAXONOMY_VERSION, "primary": None, "subcode": None, "level": None,
              "evidence": None, "secondary": [], "silent": None, "flags": flags(task, attempt, events, passed)}
    if passed:
        return result
    findings = []
    structural = [f for f in (d(task, attempt, events) for d in STRUCTURAL_DETECTORS) if f]
    behavioural = [f for f in (d(task, attempt, events) for d in BEHAVIOURAL_DETECTORS) if f]
    outcome = [f for f in (d(task, attempt, events) for d in OUTCOME_DETECTORS) if f]
    if structural:
        primary = structural[0]
        findings = structural[1:] + behavioural + outcome
    elif behavioural:
        order = {c: i for i, c in enumerate(BEHAVIOURAL)}
        behavioural.sort(key=lambda f: (f["seq"] if f["seq"] is not None else 10 ** 9, order[f["category"]]))
        primary = behavioural[0]
        findings = behavioural[1:] + outcome
    elif outcome:
        primary = outcome[0]
        findings = outcome[1:]
    else:
        primary = _finding("unclassified", None, None, "no_rule_matched")
    result.update(primary=primary["category"], subcode=primary["subcode"],
                  level=CATEGORIES[primary["category"]]["level"],
                  evidence={"seq": primary["seq"], "rule": primary["rule"]},
                  secondary=findings, silent=is_silent(primary, events, attempt))
    return result
