"""webapp-eval command line: grade, selfcheck, agent, judge, report."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness import grading

ROOT = grading.ROOT


def cmd_grade(a: argparse.Namespace) -> int:
    r = grading.grade(a.task, Path(a.patch) if a.patch else None, Path(a.out).resolve())
    print(json.dumps({k: r[k] for k in ("verdict", "seconds")} | {"failed": [c["name"] for c in r["checks"] if not c["pass"]]}))
    return 0


def cmd_selfcheck(a: argparse.Namespace) -> int:
    """Every verifier must accept the reference and the alternative fix and
    reject the untouched start state and every known-wrong patch."""
    jobs = [(t, *v) for t in (a.tasks or grading.task_ids()) for v in grading.variants(t)]
    out_root = ROOT / a.out

    def run(job):
        task, name, patch, expected = job
        r = grading.grade(task, patch, out_root / task / name)
        ok = r["verdict"] == expected
        failed = [c["name"] for c in r["checks"] if not c["pass"]]
        print(f"{'ok ' if ok else 'BAD'} {task:28} {name:28} {r['verdict']:5} (want {expected}) {r['seconds']:6}s {failed[:3]}", flush=True)
        return {"task": task, "variant": name, "expected": expected, "verdict": r["verdict"], "ok": ok,
                "failed_checks": failed, "seconds": r["seconds"]}

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        rows = list(ex.map(run, jobs))
    summary = {"rows": rows, "total": len(rows), "agree": sum(r["ok"] for r in rows)}
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{summary['agree']}/{summary['total']} variants graded as expected")
    return 0 if summary["agree"] == summary["total"] else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="webeval")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade", help="grade one patch for one task")
    g.add_argument("task")
    g.add_argument("patch", nargs="?")
    g.add_argument("--out", default=".cache/grade")
    g.set_defaults(fn=cmd_grade)
    s = sub.add_parser("selfcheck", help="grade reference, alternative and known-bad patches")
    s.add_argument("tasks", nargs="*")
    s.add_argument("-j", "--jobs", type=int, default=2)
    s.add_argument("--out", default="results/selfcheck")
    s.set_defaults(fn=cmd_selfcheck)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
