"""Fast checks of the harness itself; the verifiers are checked by `selfcheck`."""

import json
import unittest
from pathlib import Path

from harness import agent, grading, judge


class TaskLayout(unittest.TestCase):
    def test_every_task_is_complete(self):
        ids = grading.task_ids()
        self.assertGreaterEqual(len(ids), 8)
        for t in ids:
            d = grading.TASKS / t
            meta = json.loads((d / "task.json").read_text())
            self.assertEqual(meta["id"], t)
            self.assertTrue((d / "issue.md").read_text().startswith("# "), t)
            self.assertTrue(list((d / "verify").glob("*.spec.ts")), t)
            names = [v[0] for v in grading.variants(t)]
            self.assertIn("solution", names)
            self.assertTrue(any(n.startswith("alt") for n in names), f"{t}: needs an alternative fix")
            self.assertGreaterEqual(sum(n.startswith("bad-") for n in names), 2, f"{t}: needs known-bad patches")

    def test_patches_never_touch_verifiers_or_lockfile(self):
        for p in grading.TASKS.glob("*/**/*.patch"):
            text = p.read_text()
            self.assertNotIn("pnpm-lock.yaml", text, p)
            self.assertNotIn("/verify/", text, p)


class Judge(unittest.TestCase):
    def test_parse_verdict(self):
        self.assertEqual(judge.parse_verdict('Sure.\n{"verdict": "pass", "reason": "ok"}'), "pass")
        self.assertEqual(judge.parse_verdict('```json\n{"reason": "no 409", "verdict": "FAIL"}\n```'), "fail")
        self.assertEqual(judge.parse_verdict("I think it works"), "unparsed")

    def test_agreement(self):
        # 3 TP, 1 FN, 1 FP, 5 TN: po = 0.8, pe = (4*4 + 6*6) / 100 = 0.52
        pairs = [("pass", "pass")] * 3 + [("pass", "fail")] + [("fail", "pass")] + [("fail", "fail")] * 5
        a = judge.agreement(pairs)
        self.assertEqual((a["tp"], a["fn"], a["fp"], a["tn"]), (3, 1, 1, 5))
        self.assertEqual(a["accuracy"], 0.8)
        self.assertAlmostEqual(a["kappa"], (0.8 - 0.52) / 0.48, places=3)
        self.assertEqual(a["false_accept_rate"], round(1 / 6, 3))

    def test_unparsed_verdicts_are_left_out(self):
        self.assertEqual(judge.agreement([("pass", "unparsed")])["n"], 0)


class AgentTrace(unittest.TestCase):
    def test_sanitize_strips_host_paths(self):
        work = Path("/var/folders/x/T/webeval-abc")
        home = str(Path.home())
        text = f'{{"cwd": "{work}/src", "p": "{home}/projects/kezek"}}'
        clean = agent.sanitize(text, work)
        self.assertNotIn(home, clean)
        self.assertIn("$WORK/src", clean)

    def test_touched_outside_flags_reads_of_the_benchmark(self):
        work = Path("/tmp/w")
        line = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": f"cat {grading.ROOT}/tasks/t01/solution.patch"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/w/src/lib/slots.ts"}},
        ]}})
        hits = agent.touched_outside(line, work)
        self.assertEqual(len(hits), 1)
        self.assertIn("solution.patch", hits[0])


if __name__ == "__main__":
    unittest.main()
