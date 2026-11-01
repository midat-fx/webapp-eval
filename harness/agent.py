"""Runs Claude Code headless on one task and grades what it leaves behind.

The agent works in a throwaway copy of the task's start state on the host,
outside this repository, with web tools disabled. Only its diff crosses over
into the grading container, which has no network at all.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from harness import grading

ROOT = grading.ROOT
BASE = grading.CACHE / "kezek-base"
SHA = (ROOT / "base" / "kezek.sha").read_text().strip()

PROMPT = """You are working in the repository in the current directory: kezek, an
online booking app (Next.js 16 App Router, PostgreSQL via Drizzle, Redis).

Resolve the issue below by changing the code. Dependencies are installed;
`pnpm test` (unit tests) and `pnpm build` work. Postgres and Redis are not
running here, so the integration tests and the dev server won't work. Don't
add dependencies. Don't commit; leave your changes in the working tree.
Your change will be checked by hidden end-to-end tests against the issue.

---

{issue}
"""


def run(cmd: list[str], cwd: Path | None = None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, **kw)


def ensure_base() -> Path:
    """The pinned app plus the offline patch, with node_modules, cached once."""
    if (BASE / "node_modules").exists():
        return BASE
    shutil.rmtree(BASE, ignore_errors=True)
    run(["git", "clone", "-q", "https://github.com/midat-fx/kezek", str(BASE)])
    run(["git", "checkout", "-q", SHA], cwd=BASE)
    run(["git", "apply", str(ROOT / "base" / "offline.patch")], cwd=BASE)
    run(["pnpm", "install", "--frozen-lockfile", "--prefer-offline"], cwd=BASE)
    return BASE


def prepare_workdir(task: str) -> Path:
    """Fresh copy of the task start state as a one-commit git repo (no kezek history)."""
    base = ensure_base()
    work = Path(tempfile.mkdtemp(prefix="webeval-"))
    shutil.rmtree(work)
    # APFS clonefile: node_modules costs no disk per run.
    run(["cp", "-cR", str(base), str(work)])
    shutil.rmtree(work / ".git")
    setup = ROOT / "tasks" / task / "setup.patch"
    if setup.exists() and setup.stat().st_size:
        run(["git", "apply", "--whitespace=nowarn", str(setup)], cwd=work)
    run(["git", "init", "-q", "-b", "main"], cwd=work)
    run(["git", "add", "-A"], cwd=work)
    run(["git", "-c", "user.name=kezek", "-c", "user.email=dev@kezek.local", "commit", "-qm", "initial"], cwd=work)
    return work


def agent_env() -> dict[str, str]:
    # Drop the parent session's Claude Code variables so the child is a plain
    # CLI run with the user's own login.
    return {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "CLAUDE_PID"))}


def sanitize(text: str, work: Path) -> str:
    """Traces are published: no host paths in them."""
    for real in {str(work), str(work.resolve())}:
        text = text.replace(real, "$WORK")
    return text.replace(str(Path.home()), "~")


def attempt(task: str, model: str, out: Path, timeout: int = 1800) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    work = prepare_workdir(task)
    issue = (ROOT / "tasks" / task / "issue.md").read_text()
    cmd = [
        "claude", "-p", PROMPT.format(issue=issue),
        "--model", model,
        "--safe-mode",
        "--permission-mode", "bypassPermissions",
        "--disallowedTools", "WebFetch", "WebSearch",
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
    ]
    t0 = time.monotonic()
    timed_out = False
    with open(out / "trace.raw.jsonl", "w") as trace:
        proc = subprocess.Popen(cmd, cwd=work, env=agent_env(), stdout=trace, stderr=subprocess.PIPE, text=True)
        try:
            _, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, err = proc.communicate()
            timed_out = True
    elapsed = round(time.monotonic() - t0, 1)

    raw = (out / "trace.raw.jsonl").read_text()
    (out / "trace.jsonl").write_text(sanitize(raw, work))
    (out / "trace.raw.jsonl").unlink()
    run(["git", "add", "-A"], cwd=work)
    diff = run(["git", "diff", "--cached", "--binary", "HEAD"], cwd=work).stdout
    (out / "patch.diff").write_text(diff)

    final = next((json.loads(l) for l in reversed(raw.splitlines()) if '"type":"result"' in l), {})
    init = next((json.loads(l) for l in raw.splitlines() if '"subtype":"init"' in l), {})
    meta = {
        "task": task,
        "model": model,
        "served_model": init.get("model"),
        "claude_version": run(["claude", "--version"]).stdout.strip(),
        "seconds": elapsed,
        "timed_out": timed_out,
        "exit_code": proc.returncode,
        "num_turns": final.get("num_turns"),
        "cost_usd": final.get("total_cost_usd"),
        "is_error": final.get("is_error"),
        "result_text": (final.get("result") or "")[:2000],
        "stderr": sanitize(err or "", work)[-2000:],
        "patch_lines": diff.count("\n"),
        "touched_outside_workdir": touched_outside(raw, work),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    shutil.rmtree(work, ignore_errors=True)

    result = grading.grade(task, out / "patch.diff", out / "grade") if diff.strip() else empty_result(task, out / "grade")
    return meta | {"verdict": result["verdict"]}


def empty_result(task: str, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    r = {"verdict": "fail", "reason": "empty_patch", "checks": [], "task": task, "seconds": 0}
    (out / "result.json").write_text(json.dumps(r, indent=2) + "\n")
    return r


def touched_outside(raw: str, work: Path) -> list[str]:
    """Tool calls that mention the benchmark, the kezek checkout, or ~/projects.

    A cheap contamination check: the agent runs on the host, so nothing but
    this audit stops it from reading the hidden verifiers.
    """
    needles = [str(ROOT), str(Path.home() / "projects"), "webapp-eval", "kezek.git", "github.com/midat-fx"]
    hits = []
    for line in raw.splitlines():
        if '"tool_use"' not in line:
            continue
        for block in json.loads(line).get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            blob = json.dumps(block.get("input", {}))
            if any(n in blob for n in needles):
                hits.append(sanitize(blob, work)[:300])
    return hits
