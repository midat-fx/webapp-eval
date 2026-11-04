"""webapp-eval command line: grade, selfcheck, agent, judge, report."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness import grading

ROOT = grading.ROOT


def low_disk(a: argparse.Namespace, what: str) -> bool:
    """True (and says so) when free disk is under --min-free-gb: a grading
    image plus build output can fill the last few GB and take the host down."""
    free = shutil.disk_usage(ROOT).free / 2**30
    if free < a.min_free_gb:
        print(f"SKIP {what}: {free:.1f} GB free, under {a.min_free_gb} GB", flush=True)
        return True
    return False


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
        done = out_root / task / name / "result.json"
        if a.resume and done.exists() and json.loads(done.read_text())["verdict"] in ("pass", "fail"):
            r = json.loads(done.read_text())
        elif low_disk(a, f"{task} {name}"):
            return {"task": task, "variant": name, "expected": expected, "verdict": "not_graded", "ok": False,
                    "failed_checks": [], "seconds": 0}
        else:
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


MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}


def cmd_agent(a: argparse.Namespace) -> int:
    """Real agent runs. Every invocation is appended to the ledger, so the
    run budget can be audited from results/ alone."""
    from harness import agent

    out_root = ROOT / a.out
    ledger = out_root / "ledger.jsonl"
    out_root.mkdir(parents=True, exist_ok=True)
    jobs = [
        (t, m, n)
        for n in range(1, a.attempts + 1)
        for t in (a.tasks or grading.task_ids())
        for m in a.models
        if not (out_root / m / t / f"a{n}" / "meta.json").exists()
    ]
    budget_used = sum(1 for _ in ledger.open()) if ledger.exists() else 0
    if budget_used + len(jobs) > a.budget:
        print(f"refusing: {budget_used} runs used, {len(jobs)} requested, budget {a.budget}")
        return 2

    def run(job):
        task, model, n = job
        if low_disk(a, f"{model} {task} a{n}"):  # before the ledger: a skipped run costs no budget
            return None
        with ledger.open("a") as f:
            f.write(json.dumps({"task": task, "model": model, "attempt": n}) + "\n")
        r = agent.attempt(task, MODELS[model], out_root / model / task / f"a{n}", sandbox=a.sandbox)
        print(f"{model:6} {task:28} a{n} {r['verdict']:5} {r['seconds']:7}s turns={r['num_turns']} cost={r['cost_usd']}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(run, jobs))
    return 0


def cmd_judge(a: argparse.Namespace) -> int:
    from harness import judge

    model = MODELS.get(a.model, a.model)
    out_root = ROOT / "results" / "judge" / (a.model + ("-repo" if a.repo else ""))
    todo = [it for it in judge.items() if not (out_root / f"{it['id']}.json").exists() and (not a.ids or it["id"] in a.ids)]
    print(f"{len(todo)} patches to judge with {model}")

    def run(it):
        r = judge.judge(it["task"], it["patch"], model, with_repo=a.repo)
        path = out_root / f"{it['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {k: it[k] for k in ("id", "task", "source", "truth")} | r
        path.write_text(json.dumps(row, indent=2) + "\n")
        print(f"{it['id']:60} truth={it['truth']:4} judge={r['verdict']}", flush=True)

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(run, todo))

    rows = [json.loads(p.read_text()) for p in sorted(out_root.rglob("*.json")) if p.name != "summary.json"]
    pairs = lambda rs: [(r["truth"], r["verdict"]) for r in rs]
    summary = {"model": model, "overall": judge.agreement(pairs(rows)),
               "unparsed": sum(r["verdict"] == "unparsed" for r in rows),
               "by_source": {src: judge.agreement(pairs([r for r in rows if r["source"] == src]))
                             for src in sorted({r["source"] for r in rows})}}
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


def cmd_flake(a: argparse.Namespace) -> int:
    """Grade the same variant N times: how often a race-dependent verifier
    catches a wrong patch, and how often a correct one survives."""
    want = {v[0]: v for v in grading.variants(a.task)}[a.variant]
    out_root = ROOT / "results" / "flake" / a.task / a.variant
    verdicts = []
    for i in range(1, a.n + 1):
        r = grading.grade(a.task, want[1], out_root / f"run{i}")
        verdicts.append(r["verdict"])
        print(f"{a.task} {a.variant} run{i}: {r['verdict']} {r['seconds']}s", flush=True)
    summary = {"task": a.task, "variant": a.variant, "expected": want[2], "verdicts": verdicts,
               "as_expected": sum(v == want[2] for v in verdicts), "n": a.n}
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    return 0


def cmd_mutants(a: argparse.Namespace) -> int:
    """Grade the reference fix minus one hunk, for every source hunk of every task."""
    from harness import mutants

    out_root = ROOT / a.out
    jobs = []
    plan = {}
    for task in a.tasks or grading.task_ids():
        text = (grading.TASKS / task / "solution.patch").read_text()
        hs = mutants.hunks(text)
        plan[task] = hs
        jobs += [(task, i, h, text) for i, h in enumerate(hs) if mutants.gradable(h)]

    def run(job):
        task, i, h, text = job
        d = out_root / task / f"h{i:02}"
        done = d / "result.json"
        if done.exists() and json.loads(done.read_text())["verdict"] in ("pass", "fail"):
            r = json.loads(done.read_text())
        elif low_disk(a, f"{task} h{i:02}"):
            return task, {"hunk": i, "file": h.path, "outcome": "not_graded"}
        else:
            d.mkdir(parents=True, exist_ok=True)
            (d / "mutant.diff").write_text(mutants.drop(text, i))
            r = grading.grade(task, d / "mutant.diff", d)
        row = {"hunk": i, "file": h.path, "title": h.title, "outcome": mutants.outcome(r), "reason": r.get("reason"),
               "failed_checks": [c["name"] for c in r["checks"] if not c["pass"]], "seconds": r["seconds"]}
        print(f"{row['outcome']:9} {task:28} h{i:02} {h.path} {r['seconds']}s {row['failed_checks'][:2]}", flush=True)
        return task, row

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        done_rows = list(ex.map(run, jobs))
    clean = True
    for task, hs in plan.items():
        rows = [row for t, row in done_rows if t == task]
        count = lambda o: sum(r["outcome"] == o for r in rows)
        clean = clean and not (count("error") or count("invalid") or count("not_graded"))
        summary = {"task": task, "hunks": len(hs), "not_source": sum(not mutants.gradable(h) for h in hs),
                   "graded": len(rows) - count("not_graded"), "killed": count("killed"), "broken": count("broken"),
                   "survived": count("survived"), "invalid": count("invalid"), "error": count("error"), "rows": rows}
        (out_root / task).mkdir(parents=True, exist_ok=True)
        (out_root / task / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"{task}: {summary['killed']} killed, {summary['broken']} broken, {summary['survived']} survived")
    return 0 if clean else 1


def cmd_regrade(a: argparse.Namespace) -> int:
    """Re-grade saved agent patches whose grading is missing or hit an infra
    error. Re-grading never re-runs the agent, so it costs no run budget."""
    out_root = ROOT / a.out
    for meta in sorted(out_root.glob("*/*/a*/meta.json")):
        run = meta.parent
        res = run / "grade" / "result.json"
        if res.exists() and json.loads(res.read_text())["verdict"] in ("pass", "fail") and not a.all:
            continue
        task = json.loads(meta.read_text())["task"]
        if a.tasks and task not in a.tasks or a.attempt and run.name != f"a{a.attempt}":
            continue
        if low_disk(a, str(run.relative_to(out_root))):
            continue
        patch = run / "patch.diff"
        r = grading.grade(task, patch, run / "grade") if patch.read_text().strip() else None
        print(f"{run.relative_to(out_root)}: {r['verdict'] if r else 'empty patch'}", flush=True)
    return 0


def cmd_scrub(a: argparse.Namespace) -> int:
    """Re-apply trace sanitising to every published agent trace (idempotent)."""
    from harness import agent

    for t in sorted((ROOT / "results" / "agent").glob("*/*/a*/trace.jsonl")):
        text = t.read_text()
        clean = agent.sanitize(text, Path("/nonexistent-workdir"))
        if clean != text:
            t.write_text(clean)
            print(f"scrubbed {t.relative_to(ROOT)}")
    return 0


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
    s.add_argument("--min-free-gb", type=int, default=12)
    s.add_argument("--resume", action="store_true", help="reuse existing pass/fail results")
    s.set_defaults(fn=cmd_selfcheck)
    ag = sub.add_parser("agent", help="run Claude Code headless on tasks and grade the result")
    ag.add_argument("tasks", nargs="*")
    ag.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    ag.add_argument("--attempts", type=int, default=1)
    ag.add_argument("--budget", type=int, default=60)
    ag.add_argument("-j", "--jobs", type=int, default=2)
    ag.add_argument("--min-free-gb", type=int, default=12)
    ag.add_argument("--out", default="results/agent")
    ag.add_argument("--sandbox", action="store_true", help="run claude under harness/agent.sb (macOS sandbox-exec)")
    ag.set_defaults(fn=cmd_agent)
    j = sub.add_parser("judge", help="LLM judge over every graded patch, scored against the verifiers")
    j.add_argument("--model", default="sonnet")
    j.add_argument("-j", "--jobs", type=int, default=3)
    j.add_argument("--repo", action="store_true", help="give the judge read-only tools in the task's start state")
    j.add_argument("--ids", nargs="+", help="judge only these item ids (e.g. selfcheck/t04-sse-subscriber-leak/alt)")
    j.set_defaults(fn=cmd_judge)
    fl = sub.add_parser("flake", help="grade one variant repeatedly")
    fl.add_argument("task")
    fl.add_argument("variant")
    fl.add_argument("-n", type=int, default=5)
    fl.set_defaults(fn=cmd_flake)
    mu = sub.add_parser("mutants", help="grade the reference fix minus one hunk at a time")
    mu.add_argument("tasks", nargs="*")
    mu.add_argument("-j", "--jobs", type=int, default=2)
    mu.add_argument("--out", default="results/mutants")
    mu.add_argument("--min-free-gb", type=int, default=12)
    mu.set_defaults(fn=cmd_mutants)
    rg = sub.add_parser("regrade", help="re-grade saved agent patches (missing or infra-error results)")
    rg.add_argument("tasks", nargs="*")
    rg.add_argument("--all", action="store_true")
    rg.add_argument("--attempt", type=int, help="only runs a<N>, e.g. 1 for the first attempt of every cell")
    rg.add_argument("--min-free-gb", type=int, default=12)
    rg.add_argument("--out", default="results/agent")
    rg.set_defaults(fn=cmd_regrade)
    sc = sub.add_parser("scrub", help="strip host paths and account events from published traces")
    sc.set_defaults(fn=cmd_scrub)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
