"""LLM-as-judge baseline: reads the issue and the diff, says pass or fail.

It sees exactly what a reviewer skimming a PR sees — no repository, no tools,
no way to run anything — and is scored against the deterministic verdicts.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from harness import agent, grading

ROOT = grading.ROOT

PROMPT = """You are reviewing a patch to kezek, an online booking app (Next.js 16
App Router, PostgreSQL via Drizzle ORM, Redis). The patch claims to resolve the
issue below. Decide whether it fully resolves the issue as written, including
every requirement and edge case the issue states, without breaking existing
behaviour. Judge only from the issue and the diff.

Reply with one JSON object and nothing else:
{{"verdict": "pass" or "fail", "reason": "<one or two sentences>"}}

## Issue

{issue}

## Patch

```diff
{patch}
```
"""

MAX_PATCH = 60_000

REPO_NOTE = """
The repository is in the current directory at the state *before* the patch.
You may read it (Read, Grep, Glob) to check what the diff relies on.
"""


def judge(task: str, patch: Path, model: str, with_repo: bool = False) -> dict:
    """Without the repo: issue + diff only, no tools. With it: the same prompt,
    plus read-only tools in a fresh copy of the task's start state."""
    issue = (ROOT / "tasks" / task / "issue.md").read_text()
    diff = patch.read_text()[:MAX_PATCH]
    prompt = PROMPT.format(issue=issue, patch=diff)
    work = agent.prepare_workdir(task) if with_repo else None
    cmd = ["claude", "-p", prompt + (REPO_NOTE if with_repo else ""), "--model", model, "--safe-mode",
           "--tools", "Read,Grep,Glob" if with_repo else "", "--output-format", "json", "--no-session-persistence"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=agent.agent_env(), timeout=900,
                              cwd=work or "/")
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)
    out = json.loads(proc.stdout or "{}")
    text = out.get("result") or ""
    return {"verdict": parse_verdict(text), "raw": text[:1500], "cost_usd": out.get("total_cost_usd"),
            "is_error": out.get("is_error"), "num_turns": out.get("num_turns"), "with_repo": with_repo}


def parse_verdict(text: str) -> str:
    m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", text, re.S)
    if m:
        try:
            v = json.loads(m.group(0)).get("verdict", "").lower()
            if v in ("pass", "fail"):
                return v
        except json.JSONDecodeError:
            pass
    m = re.search(r"\"verdict\"\s*:\s*\"(pass|fail)\"", text, re.I)
    return m.group(1).lower() if m else "unparsed"


def items() -> list[dict]:
    """Every graded, non-empty patch: verifier self-check variants and agent runs."""
    out = []
    for summary in (ROOT / "results" / "selfcheck").glob("summary.json"):
        for row in json.loads(summary.read_text())["rows"]:
            if row["variant"] == "baseline":
                continue
            v = row["variant"]
            t = ROOT / "tasks" / row["task"]
            patch = t / ("solution.patch" if v == "solution" else f"{v}.patch" if v.startswith("alt") else f"bad/{v[4:]}.patch")
            out.append({"id": f"selfcheck/{row['task']}/{v}", "task": row["task"], "patch": patch,
                        "source": "reference" if v == "solution" or v.startswith("alt") else "known-bad",
                        "truth": row["verdict"]})
    for meta in sorted((ROOT / "results" / "agent").glob("*/*/a*/meta.json")):
        run = meta.parent
        result = run / "grade" / "result.json"
        if not result.exists() or not (run / "patch.diff").read_text().strip():
            continue
        truth = json.loads(result.read_text())["verdict"]
        if truth not in ("pass", "fail"):
            continue
        out.append({"id": f"agent/{run.relative_to(ROOT / 'results' / 'agent')}", "task": json.loads(meta.read_text())["task"],
                    "patch": run / "patch.diff", "source": "agent", "truth": truth})
    return out


def agreement(pairs: list[tuple[str, str]]) -> dict:
    """Confusion matrix, accuracy and Cohen's kappa of (truth, judged) pairs."""
    pairs = [(t, j) for t, j in pairs if j in ("pass", "fail")]
    n = len(pairs)
    tp = sum(1 for t, j in pairs if t == "pass" and j == "pass")
    tn = sum(1 for t, j in pairs if t == "fail" and j == "fail")
    fp = sum(1 for t, j in pairs if t == "fail" and j == "pass")
    fn = sum(1 for t, j in pairs if t == "pass" and j == "fail")
    if n == 0:
        return {"n": 0}
    po = (tp + tn) / n
    pe = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / (n * n)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return {"n": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn, "accuracy": round(po, 3), "kappa": round(kappa, 3),
            "false_accept_rate": round(fp / (fp + tn), 3) if fp + tn else None,
            "false_reject_rate": round(fn / (fn + tp), 3) if fn + tp else None}
