"""Builds results/summary.json and the tables in README.md from results/."""

from __future__ import annotations

import json
import re
import statistics
import sys
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


def agents(root: Path = RES / "agent") -> dict:
    rows = []
    for meta in sorted(root.glob("*/*/a*/meta.json")):
        m = load(meta)
        g = meta.parent / "grade" / "result.json"
        m["verdict"] = load(g)["verdict"] if g.exists() else "missing"
        m["run"] = str(meta.parent.relative_to(root))
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
    ledger = root / "ledger.jsonl"
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


def timing() -> dict:
    """Wall time per grading, from every published result.json that got as far as
    the checks. Builds that failed stop early and would drag the median down."""
    by_task = defaultdict(list)
    for p in RES.rglob("result.json"):
        r = load(p)
        if r.get("checks") and isinstance(r.get("seconds"), (int, float)):
            by_task[r["task"]].append(r["seconds"])
    def stats(xs):
        xs = sorted(xs)
        p90 = statistics.quantiles(xs, n=10, method="inclusive")[8] if len(xs) > 1 else xs[0]
        return {"n": len(xs), "p50": round(statistics.median(xs), 1), "p90": round(p90, 1), "max": xs[-1]}
    out = {"by_task": {t: stats(xs) for t, xs in sorted(by_task.items())},
           "all": stats([x for xs in by_task.values() for x in xs])}
    return out


NAMES = {"claude-haiku-5-5": "Haiku 5.5", "claude-sonnet-5-5": "Sonnet 5.5"}


def collect() -> dict:
    # t11 and the sandboxed runs came after the 60-run budget; each has its own ledger.
    return {"selfcheck": selfcheck(), "agents": agents(), "agents_t11": agents(RES / "agent-t11"),
            "agents_sandbox": agents(RES / "agent-sandbox"), "judge": judges(), "flake": flakes(),
            "mutants": mutants(), "timing": timing()}


def tables(out: dict) -> dict[str, str]:
    """The README tables, generated so they can't drift from results/."""
    ag, mu, ti = out["agents"], out["mutants"], out["timing"]
    models = sorted(ag["totals"])
    row = lambda *cells: "| " + " | ".join(str(c) for c in cells) + " |"
    st = lambda m, k: ag["stats"][m][k]
    agents_md = [row("Task", *(NAMES.get(m, m) for m in models)), "|---|" + "---|" * len(models)]
    agents_md += [row(t, *(f"{c.get(m, [0, 0])[0]}/{c.get(m, [0, 0])[1]}" for m in models)) for t, c in ag["table"].items()]
    agents_md += [row("**total**", *(f"**{ag['totals'][m][0]}/{ag['totals'][m][1]}**" for m in models)),
                  row("mean wall time", *(f"{st(m, 'mean_seconds'):.0f} s" for m in models)),
                  row("mean turns", *(f"{st(m, 'mean_turns'):.1f}" for m in models)),
                  row("mean cost (CLI-reported)", *(f"${st(m, 'mean_cost_usd'):.2f}" for m in models))]
    mutants_md = [row("Task", "Hunks", "Rejected by a verifier", "Didn't build", "Survived"), "|---|---|---|---|---|"]
    mutants_md += [row(t, m["hunks"], m["killed"], m["broken"], m["survived"]) for t, m in mu["by_task"].items()]
    mutants_md += [row("**total**", *(f"**{mu[k]}**" for k in ("hunks", "killed", "broken", "survived")))]
    timing_md = [row("Task", "Gradings", "p50", "p90"), "|---|---|---|---|"]
    timing_md += [row(t, m["n"], f"{m['p50']:.0f} s", f"{m['p90']:.0f} s") for t, m in ti["by_task"].items()]
    a = ti["all"]
    timing_md += [row("**all**", f"**{a['n']}**", f"**{a['p50']:.0f} s**", f"**{a['p90']:.0f} s**")]
    return {"agents": "\n".join(agents_md), "mutants": "\n".join(mutants_md), "timing": "\n".join(timing_md)}


def readme_blocks(text: str) -> dict[str, str]:
    return dict(re.findall(r"<!-- report:(\w+) -->\n(.*?)\n<!-- /report:\1 -->", text, re.S))


def write_readme(out: dict) -> None:
    path = ROOT / "README.md"
    text = path.read_text()
    for name, md in tables(out).items():
        text = re.sub(rf"(<!-- report:{name} -->\n).*?(\n<!-- /report:{name} -->)",
                      lambda m: m.group(1) + md + m.group(2), text, flags=re.S)
    path.write_text(text)


def main() -> None:
    out = collect()
    (RES / "summary.json").write_text(json.dumps(out, indent=2) + "\n")
    (RES / "timing.json").write_text(json.dumps(out["timing"], indent=2) + "\n")
    if "--readme" in sys.argv:
        write_readme(out)
    sc, ag = out["selfcheck"], out["agents"]
    print(f"Verifier self-check: {sc['agree']}/{sc['total']} variants as expected; "
          f"known-bad caught {sc['known_bad_caught']}/{sc['known_bad']}\n")
    md = tables(out)
    print(md["agents"])
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
    print(md["mutants"])
    print(f"verifier gaps found and closed: {mu['gaps_found']}")
    for x in mu["survivors"]:
        print(f"  {x['mutant']} {x['file']}: {x['class']}")
    print("\n" + md["timing"])


if __name__ == "__main__":
    main()
