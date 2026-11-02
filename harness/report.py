"""Builds results/summary.json and the tables in README.md from results/."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from harness import grading

ROOT = grading.ROOT
RES = ROOT / "results"


def load(p: Path):
    return json.loads(p.read_text())


def selfcheck() -> dict:
    s = load(RES / "selfcheck" / "summary.json")
    by_task = defaultdict(lambda: {"accepted": [], "rejected": [], "wrong": []})
    for r in s["rows"]:
        key = "wrong" if not r["ok"] else ("accepted" if r["verdict"] == "pass" else "rejected")
        by_task[r["task"]][key].append(r["variant"])
    bad = [r for r in s["rows"] if r["variant"].startswith("bad-")]
    return {"agree": s["agree"], "total": s["total"], "known_bad": len(bad),
            "known_bad_caught": sum(r["verdict"] == "fail" for r in bad), "by_task": dict(by_task)}


def agents() -> dict:
    rows = []
    for meta in sorted((RES / "agent").glob("*/*/a*/meta.json")):
        m = load(meta)
        g = meta.parent / "grade" / "result.json"
        m["verdict"] = load(g)["verdict"] if g.exists() else "missing"
        m["run"] = str(meta.parent.relative_to(RES / "agent"))
        rows.append(m)
    table = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        cell = table[r["task"]][r["model"]]
        cell[0] += r["verdict"] == "pass"
        cell[1] += 1
    models = sorted({r["model"] for r in rows})
    totals = {m: [sum(table[t][m][0] for t in table), sum(table[t][m][1] for t in table)] for m in models}
    def mean(key, m):
        xs = [r[key] for r in rows if r["model"] == m and isinstance(r.get(key), (int, float))]
        return round(sum(xs) / len(xs), 2) if xs else None
    stats = {m: {"mean_seconds": mean("seconds", m), "mean_turns": mean("num_turns", m),
                 "mean_cost_usd": mean("cost_usd", m),
                 "errors": sum(1 for r in rows if r["model"] == m and r["verdict"] not in ("pass", "fail")),
                 "served_models": sorted({r.get("served_model") or "?" for r in rows if r["model"] == m})} for m in models}
    ledger = RES / "agent" / "ledger.jsonl"
    return {"runs": len(rows), "ledger_invocations": sum(1 for _ in ledger.open()) if ledger.exists() else 0,
            "table": {t: dict(v) for t, v in sorted(table.items())}, "totals": totals, "stats": stats,
            "contamination_flags": [r["run"] for r in rows if r.get("touched_outside_workdir")]}


def judges() -> dict:
    return {p.parent.name: load(p) for p in sorted((RES / "judge").glob("*/summary.json"))}


def flakes() -> list:
    return [load(p) for p in sorted((RES / "flake").glob("*/*/summary.json"))]


def mutants() -> dict:
    """Kill rate counts only mutants that built: a compile error says nothing about a verifier."""
    d = RES / "mutants"
    notes = load(d / "classification.json") if (d / "classification.json").exists() else {}
    by_task, survivors = {}, []
    for p in sorted(d.glob("*/summary.json")):
        s = load(p)
        by_task[s["task"]] = {k: s[k] for k in ("hunks", "not_source", "graded", "killed", "broken", "survived")}
        for r in s["rows"]:
            if r["outcome"] == "survived":
                key = f"{s['task']}/h{r['hunk']:02}"
                survivors.append({"mutant": key, "file": r["file"]} | notes.get(key, {"class": "unclassified"}))
    total = lambda k: sum(t[k] for t in by_task.values())
    built = total("killed") + total("survived")
    return {"hunks": total("hunks"), "graded": total("graded"), "killed": total("killed"), "broken": total("broken"),
            "survived": total("survived"), "verifier_kill_rate": round(total("killed") / built, 3) if built else None,
            "by_task": by_task, "survivors": survivors,
            "gaps_found": [k for k, v in notes.items() if v["class"] == "gap"]}


def main() -> None:
    out = {"selfcheck": selfcheck(), "agents": agents(), "judge": judges(), "flake": flakes(), "mutants": mutants()}
    (RES / "summary.json").write_text(json.dumps(out, indent=2) + "\n")
    sc, ag = out["selfcheck"], out["agents"]
    print(f"Verifier self-check: {sc['agree']}/{sc['total']} variants as expected; "
          f"known-bad caught {sc['known_bad_caught']}/{sc['known_bad']}\n")
    models = sorted(ag["totals"])
    print("| Task | " + " | ".join(models) + " |")
    print("|---|" + "---|" * len(models))
    for t, cells in ag["table"].items():
        print(f"| {t} | " + " | ".join(f"{cells.get(m, [0, 0])[0]}/{cells.get(m, [0, 0])[1]}" for m in models) + " |")
    print("| **total** | " + " | ".join(f"**{ag['totals'][m][0]}/{ag['totals'][m][1]}**" for m in models) + " |")
    print(json.dumps(ag["stats"], indent=2))
    for name, j in out["judge"].items():
        print(f"\njudge {name}: {json.dumps(j['overall'])}")
        for src, a in j["by_source"].items():
            print(f"  {src}: {json.dumps(a)}")
    for f in out["flake"]:
        print(f"flake {f['task']} {f['variant']}: {f['as_expected']}/{f['n']} as expected ({f['expected']})")
    mu = out["mutants"]
    print(f"\nmutants: {mu['graded']} graded, {mu['killed']} killed, {mu['broken']} broken, {mu['survived']} survived, "
          f"verifier kill rate {mu['verifier_kill_rate']}")
    print("| Task | Hunks | Killed | Didn't build | Survived |\n|---|---|---|---|---|")
    for t, m in mu["by_task"].items():
        print(f"| {t} | {m['hunks']} | {m['killed']} | {m['broken']} | {m['survived']} |")
    print(f"verifier gaps found and closed: {mu['gaps_found']}")
    for x in mu["survivors"]:
        print(f"  {x['mutant']} {x['file']}: {x['class']}")


if __name__ == "__main__":
    main()
