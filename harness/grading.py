"""Host side of grading: one `docker run --network none` per (task, patch)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
CACHE = ROOT / ".cache"
IMAGE = os.environ.get("WEBEVAL_IMAGE", "webapp-eval-runner:dev")


def task_ids() -> list[str]:
    return sorted(p.name for p in TASKS.iterdir() if (p / "task.json").exists())


def variants(task: str) -> list[tuple[str, Path | None, str]]:
    """(name, patch, expected verdict) for the verifier self-check."""
    t = TASKS / task
    out: list[tuple[str, Path | None, str]] = [("baseline", None, "fail"), ("solution", t / "solution.patch", "pass")]
    for alt in sorted(t.glob("alt*.patch")):
        out.append((alt.stem, alt, "pass"))
    for bad in sorted((t / "bad").glob("*.patch")):
        out.append((f"bad-{bad.stem}", bad, "fail"))
    return out


def grade(task: str, patch: Path | None, out_dir: Path, timeout: int = 1500) -> dict:
    """Grade `patch` (None = the untouched task start state) and return result.json.

    `out_dir` gets result.json and trace.jsonl; the container's logs (build,
    server, Playwright) go to a scratch dir under .cache that is not published.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="grade-", dir=CACHE))
    cand = work / "candidate.patch"
    cand.write_bytes(patch.read_bytes() if patch else b"")
    logs = work / "out"
    logs.mkdir()
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        "--memory", os.environ.get("WEBEVAL_MEMORY", "2560m"), "--cpus", "2",
        "-v", f"{TASKS / task}:/task:ro",
        "-v", f"{cand}:/candidate.patch:ro",
        "-v", f"{logs}:/out",
        IMAGE,
    ]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
    elapsed = round(time.monotonic() - t0, 1)
    try:
        result = json.loads((logs / "result.json").read_text())
    except (OSError, json.JSONDecodeError):
        result = {"verdict": "error", "reason": f"no result (docker exit {rc})", "checks": []}
    result.update(task=task, seconds=elapsed)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if (logs / "trace.jsonl").exists():
        shutil.copy(logs / "trace.jsonl", out_dir / "trace.jsonl")
    keep = CACHE / "logs" / out_dir.relative_to(ROOT).as_posix().replace("/", "__")
    shutil.rmtree(keep, ignore_errors=True)
    try:
        shutil.move(str(logs), keep)
    except OSError:  # a killed container never handed /out back (Linux: root-owned)
        pass
    shutil.rmtree(work, ignore_errors=True)
    return result
