# Failure taxonomy of agent attempts

[Magyar](failure_taxonomy.hu.md)

Taxonomy version 2 (2026-11-27; version 1: 2026-11-26; version 2 adds `wrong_result/gave_up` after the first live run of the M1 task set). Requirements and reasons: [requirements](requirements.md), section 3 (FA-30 to
FA-39). The machine-readable source is `CATEGORIES` in `bench/core/failures.py`; a test checks that every id below matches
it. Status: implemented and tested on synthetic traces and two recorded live traces; not yet used on a full task set,
and the heuristic rules have been checked by a manual review of the failures of one live run only (FA-37, 2026-11-27: it found a gap in a task's keyword list and led to the `gave_up` subcode).

## How an attempt is categorized

Only failed attempts get a category. Each gets exactly one **primary** category with a subcode, the **evidence**
(sequence number of the trace event and the name of the rule) and the other findings as **secondary** categories.
Successful attempts can still carry **flags**.

| Level | Categories | Which one wins |
|---|---|---|
| Structural | `infra_error` > `context_overflow` > `output_truncated` > `format_invalid` | fixed order |
| Behavioural | `no_tool_when_needed`, `wrong_tool`, `wrong_arguments`, `unnecessary_tool`, `loop`, `incomplete_chain` | the finding whose first evidence comes earliest in the trace; ties in this order |
| Outcome | `limit_silent` > `ignored_tool_error` > `wrong_result` > `unclassified` | fixed order, only when there is no behavioural finding |

Reason for the behavioural rule: failures follow from each other (a wrong argument gives a tool error, the model
repeats the call, the round limit stops it). A fixed order would report the last link; the time order shows the first.

**Silent or loud.** A failure is *silent* when the user cannot notice it: the run ended normally, the answer is not
empty, is not a question, and contains none of the problem words (error, unable, timed out, limit, not found and
similar; list in `PROBLEM_SIGNALS`). Structural failures are always loud. The share of silent failures is the headline
number of the report: it corresponds to an undetected fault in functional safety. The rule is heuristic.

**What the measurement assumes.** The default system prompt asks the model to use a tool when data is missing and to
say when a tool fails; when the round limit is hit, the harness tells the model to answer and to say if the answer is
incomplete. `limit_silent` and `ignored_tool_error/not_reported` therefore measure whether the model follows these
instructions; the trace records the system prompt.

## Categories (FMEA view)

Mitigations are possible mitigations, **not measured** (task 19 will measure them). Reliability: *rule* = decided by
the trace structure; *heuristic* = depends on text matching.

| Category | Failure mode | Effect | Detection | Reliability | Possible mitigation (not measured) |
|---|---|---|---|---|---|
| `infra_error` | The harness or the SDK failed, the attempt was stopped, skipped, or its trace has no end | No statement about the model; excluded from model scores | Status `error`, `aborted`, `skipped`; an `error` event; no `task_end` | rule | Fix the environment; rerun |
| `context_overflow` | The conversation no longer fits the context | The answer is cut off or missing | Stop reason `contextLengthReached` (the harness asks LM Studio to stop at the limit) | rule | Larger context; smaller tool results; summarizing history |
| `output_truncated` | The token budget of a round ran out | Missing or partial answer | Stop reason `maxPredictedTokensReached` | rule | Larger budget per round; reasoning budget; non-thinking mode |
| `format_invalid` | The model tried to call a tool, but the call was not recognized | No tool runs; the model looks as if it ignored the tools | The SDK reported an unparsable call; or a reply without tool calls names an offered tool in call form (`"name": "<tool>"`, `<function=<tool>`, `<tool_call>`, an XML element `<tool ...>`) | heuristic (text form), rule (SDK report) | Parse text calls (repair); grammar or schema constraint; a better chat template |
| `no_tool_when_needed` | The model answered without calling a tool the task needs | Invented answer, or a question back to the user | No parsed call although the task expects calls | rule | Stronger tool instruction in the system prompt; tool choice "required" |
| `wrong_tool` | A tool that does not exist, a decoy or a forbidden tool was called | Wrong data; with a forbidden tool, an unwanted action | Call to an unknown tool; call to a `forbidden_tools` entry; a tool outside the expected calls while the expected chain is not complete | rule | Clearer tool descriptions; fewer offered tools; confirmation before destructive tools |
| `wrong_arguments` | The right tool with wrong arguments | Tool error or wrong data | Schema check failed (missing, wrong type, value outside the enum, unknown argument); or the next expected call was made with non-matching arguments | rule | Schema constraint; examples in the tool description; type coercion in the tool |
| `unnecessary_tool` | A tool was called although none was needed | Cost, latency; side effects | Calls in a task marked `no_tool_needed` | rule | Instruction to answer directly when possible |
| `loop` | The same call is repeated, or the round limit stops the model | Wasted time; no answer of its own | The same name and arguments at least `loop_threshold` times (default 3); a round limit hit in a task that does not accept it | rule | Feedback on repeated calls; lower round limit with a clear message |
| `incomplete_chain` | The model stopped before the end of a multi-step chain | Partial result presented as final | A real prefix of the expected calls was made, and the last round has no call | rule | Plan the steps first; remind of the goal after each tool result |
| `limit_silent` | A limit was hit, and the answer does not say so | The user trusts an incomplete answer | A `limit_hit` event and none of the task's failure words (or the problem words) in the answer | heuristic | Make the limit message explicit; check the answer for a limit statement |
| `ignored_tool_error` | A tool failed, and the answer ignores it | Invented result or a missing warning | A tool result with `ok = false`, and the answer contains a value from the task's deny list, or none of the failure words | `fabricated`: rule; `not_reported`: heuristic | Instruction to report tool errors; structured error results |
| `wrong_result` | The steps were right, the answer is wrong | Wrong information presented as fact | Expected calls made (or no tool needed and none called), and an answer check fails | rule | Ask the model to quote the tool result; answer format |
| `unclassified` | Failed, and no rule explains why | Gap in the taxonomy | No other finding | rule | Inspect the trace; extend the taxonomy |

### Subcodes

| Category | Subcode | Meaning |
|---|---|---|
| `infra_error` | `harness_error` | The harness reported an error |
| | `aborted` | Stopped by the user or the stop command |
| | `skipped` | Not run (the run stopped earlier) |
| | `incomplete_trace` | The trace has no `task_end` (the harness was killed) |
| `output_truncated` | `reasoning_exhausted` | The budget went into reasoning, the answer is empty |
| | `max_tokens` | The answer itself was cut off |
| `format_invalid` | `sdk_parse_failure` | The SDK reported a call it could not parse |
| | `text_tool_call` | The call was written as text in the answer |
| `no_tool_when_needed` | `asked_user` | The answer is a question |
| | `answered_without_data` | The model answered without the data |
| `wrong_tool` | `unknown_tool` | A tool name that was not offered |
| | `decoy` | An offered tool that does not lead to the answer |
| | `forbidden` | A tool the task forbids |
| `wrong_arguments` | `missing_required` | A required argument is missing |
| | `wrong_type` | Wrong type (a number sent as a string counts) |
| | `wrong_value` | A value that is not expected (also an enum or unknown-argument violation) |
| | `invented_value` | A string value found neither in the prompt nor in an earlier tool result |
| `loop` | `identical_calls` | The same call repeated |
| | `round_limit` | Stopped by the round limit |
| `limit_silent` | `rounds`, `wall_time`, `tool_timeout` | Which limit was hit |
| `ignored_tool_error` | `fabricated` | A value from the deny list in the answer |
| | `not_reported` | The failure is not mentioned |
| `wrong_result` | `empty_answer` | No answer |
| | `gave_up` | The last tool result was an error and the answer reports it, without a retry that would have succeeded (honest and loud, but the task was not done) |
| | `partial` | Some of the expected facts are missing |
| | `wrong_value` | The answer checks fail otherwise |

### Flags

Counted on every attempt, also successful ones.

| Flag | Meaning |
|---|---|
| `recovered_error` | A tool error or an invalid call happened, and the attempt still passed (baseline for task 19) |
| `redundant_calls` | Repeated identical calls, or more calls than the expected sequence |
| `parallel_calls` | More than one call in one round (an ability, not a failure) |
| `reasoning_leak` | Reasoning text or an LM Studio separator in the answer; can make a check pass falsely |
| `sandbox_escape_attempt` | `read_file` was asked for a path outside the sandbox |

## Relation to published classifications

To be checked against the sources before publication; partly taken from summaries.

| Here | Published |
|---|---|
| `format_invalid` | BFCL: AST / executable mismatch of the call format |
| `wrong_tool/unknown_tool`, `wrong_tool/decoy` | Tool selection hallucination (Xu et al., arXiv 2412.04141) |
| `wrong_arguments/invented_value` | Tool usage hallucination (same source) |
| `no_tool_when_needed/asked_user` in a task with a missing parameter | BFCL v3 "missing parameters" |
| `unnecessary_tool` | BFCL relevance / irrelevance detection |
| `loop/identical_calls` | MAST FM-1.3 step repetition (Cemri et al., arXiv 2503.13657) |
| `loop/round_limit`, `limit_silent` | MAST FM-1.5 unaware of termination conditions |
| `incomplete_chain` | MAST FM-3.1 premature termination |

## Versioning

A change of a category id, a subcode or a detection rule raises the taxonomy version; result rows record it
(`taxonomy_version`), and `bench agent report` (planned, M1 step 5b) recomputes categories from the traces, so older
runs can be categorized again with a newer version.
