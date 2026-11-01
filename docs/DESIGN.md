# Design notes

Why webapp-eval is built the way it is. Each section is a decision and the
alternative it beat.

## Tasks come from one real app, at a pinned commit

All ten tasks are cut from [kezek](https://github.com/midat-fx/kezek) at
`base/kezek.sha`: a Next.js 16 / Postgres / Redis booking app with real
concurrency (slot holds, an exclusion constraint, a transactional outbox) and
real UI state (a four-step wizard, an SSE-driven admin calendar).

- One codebase means the agent has to read a real project every time
  (App Router conventions, Drizzle, server actions). Ten toy repos would
  measure "can it read a 50-line file".
- Pinning the commit makes every start state reproducible from a clean clone:
  the image clones kezek at that SHA, nothing is vendored. A pin is only as
  good as the upstream history, though: on 2026-11-01 kezek's history was
  rewritten, and the pinned commit `99211bb` became `6242b34`. Its tree is the
  same (`a54260b`), so every patch and verdict still holds; only the pin
  changed, and the earlier results were produced against `99211bb`.

Two kinds of task:

| Origin | Tasks | How the start state is made |
|---|---|---|
| Existing behaviour at the pinned commit | t01, t02, t03, t07, t08, t09, t10 | the pinned code as is; the issue describes a real gap |
| Injected regression | t04, t05, t06 | `setup.patch` removes or breaks something that kezek gets right |

Injected regressions remove their own fingerprints: t05 drops the overlap
constraint *and* the README section, the SECURITY.md row, the integration
tests and the code comments that mention it. Otherwise the fastest "fix" is
to grep for the sentence the setup forgot to delete.

`base/offline.patch` is applied under every task: kezek loads Geist from
Google Fonts at build time, and gradings have no network.

## Verifiers check behaviour, never code

Each task has hidden verifiers of up to three kinds, all run against the
built app:

1. **Playwright scenarios** — a browser or HTTP client doing what the issue
   says a user does: book through the wizard, replay a form from devtools,
   race six checkouts across two servers.
2. **PostgreSQL invariants** (`verify/invariants.sql`) — after the scenarios,
   queries that return offending rows: overlapping confirmed bookings, two
   status changes for one booking, a waitlist offer for a booking that isn't
   cancelled. An invariant is phrased over the data, not over the code path,
   so it holds for any correct implementation.
3. **axe-core** (tagged `@axe`) — WCAG 2 A/AA scans of the UI states a task
   touches (t09 step 4, every state of the wizard in t10).

Nothing inspects the diff. An agent may restructure the code however it
likes: t04's alternative fix replaces per-connection subscribers with one
shared subscriber per process, t05's uses an advisory lock instead of a
constraint, t07's wraps actions in a higher-order function and returns 404
instead of redirecting. All pass, because they all *behave* correctly.

Verifiers touch the database directly only to arrange fixtures (a booking
that makes a day's first free slot 14:00, a staff login) and to read state
back. The one deliberate exception is t05, which places Redis holds directly
in the format `createBooking` checks (`hold:<staff>:<startMs>` →
`{token, endMs}`): it is the only way to put six racers past the hold layer
at once deterministically. A solution that changes the hold format would be
misjudged; the issue says holds stay as they are.

## A verifier is only trusted after it has been attacked

`make test` runs the **self-check**: for every task, grade

- the untouched start state — must **fail** (the verifier sees the bug),
- `solution.patch`, the reference fix — must **pass**,
- `alt.patch`, an independently written correct fix — must **pass**,
- every `bad/*.patch` — must **fail**.

The known-bad patches are the wrong fixes an agent plausibly writes:

| Pattern | Examples |
|---|---|
| Partial fix | t01 normalises phones on `/book` but not `/waitlist`; t07 guards services but not staff actions; t03 fixes the default date but not `min` |
| UI-only fix | t01 strips spaces in the browser; t06 hides out-of-hours slots in the wizard; t08 disables the button while pending; t07 hides pages but not actions |
| Fits the scenario | t06 hard-codes the 2027 DST dates from the issue; t02 drops responses slower than 2 s; t03 hard-codes UTC+5; t10 deletes the low-contrast text |
| Right idea, wrong layer | t05 serialises with an in-process mutex (two servers); t05 adds a unique index on start time (overlaps start at different times); t04 unsubscribes but never closes the connection |
| Over-correction | t07 makes *everything* owner-only, so staff can't run the day |

The alternative fix is what keeps verifiers from overfitting to the reference.
Writing it found real problems: the first t03 verifier faked the browser
clock, which a server-side fix (alt) ignores, so the check was rewritten to
use real time and many timezones instead.

Every verifier change re-runs the whole matrix; the published numbers are in
`results/selfcheck/`.

### Race checks are probabilistic

Three known-bad patches are only wrong under concurrency (t05
check-then-insert and in-process lock, t08 read-then-update). Their
verifiers race many requests over several rounds and two servers, which makes
a miss unlikely but not impossible. `harness.cli flake` grades the same patch
repeatedly and writes the catch rate to `results/flake/`. Those runs haven't
been done yet, so the README makes no claim about catch rates.

### Time-dependent checks are made time-independent

t03 ("the wizard opens on the business's today") depends on the wall clock.
Faking the browser clock was rejected (see above). Instead the verifier sets
the business timezone in turn to zones from UTC−12 to UTC+14. That range
spans 26 hours, so at any instant those zones cover two different calendar
dates, and any fix that computes "today" with a fixed offset (UTC, the
visitor's zone, a hard-coded +5) disagrees with at least one of them.

## One container per grading, no network

`docker/grade.sh` runs inside `docker run --network none`: Postgres 16,
Redis, `next build` + `next start` (two instances when the task races across
servers) and headless Chromium all live in the one container.

- **No network** is the whole sandbox for the candidate's code: it is built
  and executed, and cannot fetch anything or phone anywhere. Changing
  `package.json` or the lockfile fails the grading outright (`dependencies_changed`).
- **Fresh state**: a new cluster, migrations from the candidate's tree,
  the deterministic seed. A candidate's migration (t05) is applied exactly
  as a deploy would apply it.
- **Verifiers arrive last**: specs are copied in after the candidate is
  built, from a directory the candidate's code never sees at build time.
- One image instead of compose: on this machine colima's host port
  forwarding is broken, and a single container with loopback-only services
  also needs no orchestration in CI.

Every step appends to `trace.jsonl` (`start`, `apply`, `build`, `migrate`,
`seed`, `server`, `playwright`, `invariants`, `done`) and the verdict with
per-check detail goes to `result.json`.

## Agent runs

`harness.cli agent` runs `claude -p` (Claude Code headless) per task:

- In a fresh copy of the start state outside this repository: a one-commit
  git repo with no kezek history (so `git log` can't reveal the fix) and
  `node_modules` cloned copy-on-write (APFS `clonefile`), so `pnpm test` and
  `pnpm build` work offline.
- `--safe-mode` (no user CLAUDE.md, skills, plugins, hooks or MCP servers —
  my personal setup must not leak into the measurement),
  `--disallowedTools WebFetch WebSearch`, `--permission-mode bypassPermissions`.
- The prompt is the issue plus four lines of environment facts, identical for
  every task and model.
- The full `stream-json` transcript is saved as `trace.jsonl`, with host
  paths rewritten (`$WORK`, `~`).
- The diff (`git add -A && git diff --cached`) is the only thing graded.

The agent runs on the host, not in the grading container, because the CLI
needs an interactive login. That means nothing but policy stops it
from wandering the disk, so every trace is audited: tool calls that mention
this repository, `~/projects` or the kezek GitHub URL are listed in
`meta.json` under `touched_outside_workdir` and counted in the README.

Every invocation is appended to `results/agent/ledger.jsonl` before it
starts, so the run budget (60) is auditable from the results alone.

## The LLM judge baseline

`harness.cli judge` asks a model whether a diff resolves the issue — the
issue text and the diff, no repository, no tools — and compares its verdict
with the deterministic one on every graded patch (reference, alternative,
known-bad, agent output). This is the cheap "LLM reviews the PR" setup many
pipelines use; the point is to measure how often it accepts patches the
verifiers prove wrong. Agreement is reported as accuracy and Cohen's κ, with
false-accept and false-reject rates split by where the patch came from.

### The judge checks the verifiers too

The judge's first pass rejected two of my alternative fixes, and it was right
both times. The t09 alternative rendered the note without `white-space`
handling, so line breaks collapsed on the card; the verifier missed it
because Playwright's `toContainText` normalises whitespace. The t04
alternative could run its cleanup twice (on abort and on cancel), and the
second call could unsubscribe a tab that had opened in between. Both are
fixed. The t09 verifier now compares `innerText`, which follows CSS, and the
old alternative became `bad/collapsed-line-breaks.patch`. The first versions
and the judge's verdicts on them are kept in `results/judge/superseded/`.
That's the argument for running a cheap judge next to deterministic
verifiers: its disagreements are a list of places to look.

## Known limitations

- Ten tasks from one app: good for depth, says nothing about other stacks.
- Agent sandboxing on the host is audited, not enforced.
- Race verifiers are probabilistic, and their catch rate is not measured yet.
- t04 can't trigger the abort-then-cancel race described above
  deterministically, so a fix with that bug would still pass.
- Each grading builds the app from scratch (~10–30 s on an idle machine,
  minutes when the host is loaded); fine for tens of runs, slow for thousands.
