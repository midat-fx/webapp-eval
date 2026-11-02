"""Hunk-drop mutants of a reference patch: each one is the fix minus one hunk.

A mutant the verifiers accept points at a requirement nothing checks, or at a
hunk that doesn't matter. Telling those apart is a human call, recorded in
results/mutants/classification.json.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
# Failing here means the app never came up, so no verifier got to look at it.
NOT_BY_VERIFIER = {"build_failed", "migrate_failed", "seed_failed", "server_not_ready"}


@dataclass
class Hunk:
    path: str
    lines: list[str]  # first line is the @@ header

    @property
    def delta(self) -> int:
        body = self.lines[1:]
        return sum(s.startswith("+") for s in body) - sum(s.startswith("-") for s in body)

    @property
    def title(self) -> str:
        return HUNK.match(self.lines[0]).group(5).strip()


def parse(text: str) -> list[tuple[list[str], list[Hunk]]]:
    """Split a unified git diff into (file header lines, hunks) per file."""
    files: list[tuple[list[str], list[Hunk]]] = []
    for line in text.removesuffix("\n").split("\n"):  # not splitlines: sources may hold \f or \r
        if line.startswith("diff --git "):
            files.append(([line], []))
            continue
        header, hunks = files[-1]
        if line.startswith("@@ "):
            path = next((h[6:] for h in header if h.startswith("+++ b/")), None)
            path = path or next(h[6:] for h in header if h.startswith("--- a/"))
            hunks.append(Hunk(path, [line]))
        elif hunks:
            hunks[-1].lines.append(line)
        else:
            header.append(line)
    return files


def hunks(text: str) -> list[Hunk]:
    return [h for _, hs in parse(text) for h in hs]


def gradable(hunk: Hunk) -> bool:
    """Tests and docs can't change what the app does; don't spend a grading on them."""
    p = hunk.path
    return p.startswith(("src/", "drizzle/")) and not re.search(r"\.test\.tsx?$", p)


def drop(text: str, index: int) -> str:
    """The patch without hunk `index`. Later hunks of that file get their new-side
    line numbers corrected, because `git apply` starts looking for a hunk there."""
    out: list[str] = []
    i = 0
    for header, hs in parse(text):
        kept: list[str] = []
        shift = 0
        for h in hs:
            if i == index:
                shift = h.delta
            else:
                kept.append(_shifted(h.lines[0], shift))
                kept.extend(h.lines[1:])
            i += 1
        if kept or not hs:  # a file left with no hunks is dropped entirely
            out.extend(header)
            out.extend(kept)
    return "\n".join(out) + "\n" if out else ""


def _shifted(head: str, shift: int) -> str:
    m = HUNK.match(head)
    a, b, c, d, rest = m.groups()
    old = f"{a},{b}" if b is not None else a
    new = f"{int(c) - shift},{d}" if d is not None else str(int(c) - shift)
    return f"@@ -{old} +{new} @@{rest}"


def outcome(result: dict) -> str:
    """killed: a verifier rejected it. broken: it didn't even build or start.
    survived: every check passed. invalid/error: nothing was learned, not a kill."""
    if result["verdict"] == "pass":
        return "survived"
    if result["verdict"] != "fail":
        return "error"
    reason = result.get("reason")
    if reason == "patch_does_not_apply":
        return "invalid"
    return "broken" if reason in NOT_BY_VERIFIER else "killed"
