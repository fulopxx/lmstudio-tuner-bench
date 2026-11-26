// Offline test of the speculative decoding probe's pure parts:  node --test spec-probe-lib.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  draftRatios, firstDifference, loadConfig, median, parseSteps, speculativeFields, speculativeMismatches,
  validatePlan,
} from "./spec-probe-lib.ts";

test("plan defaults and problems", () => {
  const ok = validatePlan({ target: "a", draft: "b" });
  assert.deepEqual(ok.problems, []);
  assert.equal(ok.plan.contextLength, 4096);
  assert.deepEqual(ok.plan.mtp, []);
  assert.ok(validatePlan({ target: "<target-model-key>", draft: "b" }).problems.length);
  assert.ok(validatePlan({ target: "a", draft: "a" }).problems.length);
  assert.ok(validatePlan({ target: "a", draft: "b", repeats: 0 }).problems.length);
});

test("steps are validated and kept in order", () => {
  assert.deepEqual(parseSteps("p3,P1"), ["P1", "P3"]);
  assert.deepEqual(parseSteps(undefined), []);
  assert.throws(() => parseSteps("P1,P9"));
});

test("load config per mode", () => {
  assert.deepEqual(speculativeFields(loadConfig(4096, "off")),
    { speculativeDraftMtp: false, speculativeDraftSimple: false });
  assert.deepEqual(speculativeFields(loadConfig(4096, "draft", "d")),
    { speculativeDraftMtp: false, speculativeDraftSimple: true, speculativeDraftModel: "d" });
  assert.equal(loadConfig(4096, "mtp").speculativeDraftMtp, true);
  assert.deepEqual(speculativeFields(loadConfig(4096, "omit")), {});
  assert.equal(loadConfig(8192, "off").contextLength, 8192);
  assert.throws(() => loadConfig(4096, "draft"));
});

test("speculative mismatches compare only speculative fields", () => {
  const requested = loadConfig(4096, "draft", "d");
  assert.deepEqual(speculativeMismatches(requested, { ...requested, contextLength: 1 }), []);
  assert.equal(speculativeMismatches(requested, { ...requested, speculativeDraftModel: "" }).length, 1);
});

test("draft ratios (SD-05), n/a instead of estimates", () => {
  assert.deepEqual(draftRatios({ totalDraftTokensCount: 100, acceptedDraftTokensCount: 60 }, 200),
    { acceptanceRate: 0.6, draftShare: 0.3 });
  assert.deepEqual(draftRatios({}, 200), { acceptanceRate: null, draftShare: null });
  assert.deepEqual(draftRatios({ totalDraftTokensCount: 0, acceptedDraftTokensCount: 0 }, undefined),
    { acceptanceRate: null, draftShare: null });
});

test("median and first difference", () => {
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([1, 2, 3, 4]), 2.5);
  assert.equal(median([]), null);
  assert.equal(firstDifference("abc", "abc"), null);
  assert.equal(firstDifference("abcd", "abXd"), 2);
  assert.equal(firstDifference("ab", "abc"), 2);
});
