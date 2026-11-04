"""Fast checks of the harness itself; the verifiers are checked by `selfcheck`."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import agent, grading, judge, mutants


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


class PublishedResults(unittest.TestCase):
    def test_no_host_paths_or_account_data(self):
        bad = ("/Users/", "/var/folders/", "/private/var/", "rate_limit_event", "@gmail.com")
        for f in (grading.ROOT / "results").rglob("*"):
            if f.is_file() and f.suffix in (".json", ".jsonl", ".diff", ".md") and not f.name.endswith(".raw.jsonl"):
                text = f.read_text(errors="replace")
                for b in bad:
                    self.assertNotIn(b, text, f"{f.relative_to(grading.ROOT)} contains {b!r}")


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


class Mutants(unittest.TestCase):
    OLD = "".join(f"line {i}\n" for i in range(1, 31))

    def diff(self, repo: Path) -> str:
        return subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True, check=True).stdout

    def repo(self, tmp: str) -> Path:
        repo = Path(tmp)
        git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
        git("init", "-q")
        (repo / "a.txt").write_text(self.OLD)
        (repo / "b.txt").write_text("only line\n")
        git("add", "-A")
        git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "start")
        return repo

    def test_each_mutant_applies_and_lacks_only_its_hunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            # a.txt: two hunks, the first one grows the file so the second one shifts. b.txt: one hunk.
            lines = self.OLD.splitlines(keepends=True)
            (repo / "a.txt").write_text("".join(lines[:2] + ["new A1\n", "new A2\n"] + lines[2:25] + ["new B\n"] + lines[25:]))
            (repo / "b.txt").write_text("changed line\n")
            patch = self.diff(repo)
            subprocess.run(["git", "checkout", "-q", "."], cwd=repo, check=True)
            self.assertEqual([h.path for h in mutants.hunks(patch)], ["a.txt", "a.txt", "b.txt"])
            for i, (a_has, a_lacks, b_text) in enumerate([("new B", "new A1", "changed line\n"),
                                                          ("new A1", "new B", "changed line\n"),
                                                          ("new A1", "changed", "only line\n")]):
                mutant = repo / ".git" / f"m{i}.diff"
                mutant.write_text(mutants.drop(patch, i))
                subprocess.run(["git", "apply", "--check", str(mutant)], cwd=repo, check=True)
                subprocess.run(["git", "apply", str(mutant)], cwd=repo, check=True)
                a = (repo / "a.txt").read_text()
                self.assertIn(a_has, a)
                self.assertNotIn(a_lacks, a)
                self.assertEqual((repo / "b.txt").read_text(), b_text)
                subprocess.run(["git", "checkout", "-q", "."], cwd=repo, check=True)

    def test_later_hunk_line_numbers_follow_the_dropped_hunk(self):
        patch = ("diff --git a/x b/x\n--- a/x\n+++ b/x\n"
                 "@@ -1,1 +1,3 @@\n a\n+b\n+c\n@@ -9,1 +11,2 @@ fn\n z\n+y\n")
        self.assertIn("@@ -9,1 +9,2 @@ fn\n", mutants.drop(patch, 0))

    def test_dropping_a_files_only_hunk_drops_the_file(self):
        patch = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual(mutants.drop(patch, 0), "")

    def test_only_source_hunks_are_graded(self):
        h = lambda p: mutants.Hunk(p, ["@@ -1 +1 @@"])
        self.assertTrue(mutants.gradable(h("src/lib/slots.ts")))
        self.assertTrue(mutants.gradable(h("drizzle/0004_x.sql")))
        self.assertFalse(mutants.gradable(h("src/lib/slots.test.ts")))
        self.assertFalse(mutants.gradable(h("README.md")))

    def test_every_reference_patch_splits_into_its_hunks(self):
        for t in grading.task_ids():
            text = (grading.TASKS / t / "solution.patch").read_text()
            self.assertEqual(len(mutants.hunks(text)), text.count("\n@@ "), t)

    def test_build_failures_and_bad_applies_are_not_verifier_kills(self):
        o = lambda v, reason=None: mutants.outcome({"verdict": v, "reason": reason})
        self.assertEqual(o("pass"), "survived")
        self.assertEqual(o("fail"), "killed")
        self.assertEqual(o("fail", "build_failed"), "broken")
        self.assertEqual(o("fail", "patch_does_not_apply"), "invalid")
        self.assertEqual(o("error", "build_infra_failure"), "error")


class Readme(unittest.TestCase):
    def test_readme_tables_match_results(self):
        from harness import report
        blocks = report.readme_blocks((grading.ROOT / "README.md").read_text())
        self.assertEqual(blocks, report.tables(report.collect()), "run `python3 -m harness.report --readme`")


@unittest.skipUnless(shutil.which("sandbox-exec"), "macOS only")
class Sandbox(unittest.TestCase):
    def test_profile_denies_the_benchmark_and_allows_the_workdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp).resolve()
            (work / "f").write_text("ok")
            def can_read(path):
                cmd = agent.sandboxed(["cat", str(path)], work)
                return subprocess.run(cmd, cwd=work, capture_output=True).returncode == 0
            self.assertTrue(can_read(work / "f"))
            self.assertFalse(can_read(grading.ROOT / "tasks" / "t01-phone-format" / "solution.patch"))
            self.assertFalse(can_read(grading.ROOT / "README.md"))
            for p in (Path.home() / "projects", Path.home() / ".ssh"):
                if p.exists():
                    r = subprocess.run(agent.sandboxed(["ls", str(p)], work), cwd=work, capture_output=True)
                    self.assertNotEqual(r.returncode, 0, p)


class DiskGuard(unittest.TestCase):
    def test_low_disk_skips_only_below_the_threshold(self):
        from argparse import Namespace
        from harness import cli
        self.assertTrue(cli.low_disk(Namespace(min_free_gb=10**9), "x"))
        self.assertFalse(cli.low_disk(Namespace(min_free_gb=0), "x"))


class AgentTrace(unittest.TestCase):
    def test_sanitize_strips_host_paths(self):
        work = Path("/var/folders/x/T/webeval-abc")
        home = str(Path.home())
        text = f'{{"cwd": "{work}/src", "p": "{home}/projects/kezek"}}'
        clean = agent.sanitize(text, work)
        self.assertNotIn(home, clean)
        self.assertIn("$WORK/src", clean)

    def test_sanitize_drops_rate_limit_events(self):
        text = '{"type":"rate_limit_event","rate_limit_info":{}}\n{"type":"assistant"}\n'
        self.assertEqual(agent.sanitize(text, Path("/w")), '{"type":"assistant"}\n')

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
