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


def main() -> None:
    out = {"selfcheck": selfcheck(), "agents": agents(), "judge": judges(), "flake": flakes()}
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


if __name__ == "__main__":
    main()
