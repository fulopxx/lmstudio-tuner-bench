"""Offline test of job planning, resume selection and invalidation (no GPU, no LM Studio)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runner"))
import sweep  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class SweepLogicTest(unittest.TestCase):
    def test_quick_grid_job_count_and_size_filter(self):
        grid = json.loads((ROOT / "configs" / "quick.json").read_text(encoding="utf-8"))
        meta = {k: {"paramsString": "14B" if ("14b" in k or "12b" in k) else "8B"} for k in grid["models"]}
        jobs = sweep.build_jobs(grid, grid["models"], meta)
        large = sum(1 for k in grid["models"] if meta[k]["paramsString"] == "14B")
        for_all = sum(1 for c in grid["configs"] if "only_params" not in c)
        self.assertGreater(large, 0)
        self.assertEqual(len(jobs), for_all * len(grid["models"]) + (len(grid["configs"]) - for_all) * large)
        self.assertEqual([j["n"] for j in jobs], list(range(1, len(jobs) + 1)))
        self.assertFalse(any(j["config"].startswith("off") for j in jobs if j["model"] == "qwen3-8b"))
        self.assertNotIn("only_params", jobs[-1]["settings"])

    def test_resume_selection(self):
        jobs = [{"n": i, "id": f"m|{i}"} for i in (1, 2, 3, 4)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            sweep.append_row(p, {"job_id": "m|1", "status": "ok"})
            sweep.append_row(p, {"job_id": "m|2", "status": "timeout"})
            sweep.append_row(p, {"job_id": "m|3", "status": "ok"})
            ids = lambda **kw: [j["n"] for j in sweep.todo_jobs(jobs, sweep.latest_results(p), **kw)]
            self.assertEqual(ids(), [4])  # failed jobs are NOT retried automatically
            self.assertEqual(ids(redo_failed=True), [2, 4])
            sweep.append_row(p, {"job_id": "m|3", "status": "invalidated"})  # resume --from 3
            self.assertEqual(ids(), [3, 4])


if __name__ == "__main__":
    unittest.main()
