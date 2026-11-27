"""Offline test of ranking, warnings and recommendations."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.core import evaluate  # noqa: E402


def row(config, prompt, decode, offload=1, ctx=4096, runs=None, status="ok"):
    runs = runs or [{"prompt_tok_s": prompt, "decode_tok_s": decode}] * 2
    return {"job_id": f"m|{config}", "model": "m", "config": config, "status": status,
            "settings": {"context_length": ctx, "offload_ratio": offload, "eval_batch_size": 2048},
            "prompt_tok_s": prompt, "decode_tok_s": decode, "runs": runs, "vram_before_mib": 1000}


class EvaluateTest(unittest.TestCase):
    def test_estimate_flags_and_recommendation(self):
        rows = [row("full", 150, 14), row("off75", 520, 9, offload=0.75), row("off90", 400, 13, offload=0.9),
                row("noisy", 450, 12, offload=0.9, runs=[{"prompt_tok_s": 450, "decode_tok_s": 9},
                                                         {"prompt_tok_s": 450, "decode_tok_s": 15}])]
        a = {e["config"]: e for e in evaluate.analyze(rows, 2000, 500)["m"]}
        self.assertAlmostEqual(a["off75"]["est_s"], round(2000 / 520 + 500 / 9, 1))
        self.assertIn("spill?", a["full"]["flags"])
        self.assertNotIn("spill?", a["off75"]["flags"])
        self.assertIn("unstable", a["noisy"]["flags"])
        rec = evaluate.recommendations(evaluate.analyze(rows, 2000, 500))
        self.assertEqual([r["config"] for r in rec], ["off90"])
        self.assertEqual(rec[0]["alternative"], "")

    def test_flagged_fastest_wins_but_alternative_is_listed(self):
        rows = [row("fast-spilling", 190, 16, offload=0.9), row("clean", 520, 9, offload=0.75)]
        rec = evaluate.recommendations(evaluate.analyze(rows, 2000, 500))[0]
        self.assertEqual(rec["config"], "fast-spilling")  # measured estimate ranks, flags only warn
        self.assertIn("spill?", rec["flags"])
        self.assertTrue(rec["alternative"].startswith("clean "))

    def test_output_length_changes_the_choice(self):
        rows = [row("fast-decode", 300, 20), row("fast-prompt", 600, 12)]
        long_in = evaluate.recommendations(evaluate.analyze(rows, 8000, 50))
        long_out = evaluate.recommendations(evaluate.analyze(rows, 100, 2000))
        self.assertEqual(long_in[0]["config"], "fast-prompt")
        self.assertEqual(long_out[0]["config"], "fast-decode")

    def test_failed_rows_are_reported_not_ranked(self):
        rows = [row("ok", 300, 20), row("bad", None, None, status="timeout")]
        text = evaluate.report(rows, "x", 2000, 500)
        self.assertIn("1 failed job(s)", text)
        self.assertIn("| bad | 4096 | None | None | timeout |", text)


if __name__ == "__main__":
    unittest.main()
