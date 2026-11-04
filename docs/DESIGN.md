# Design notes

Why webapp-eval is built the way it is. Each section is a decision and the
alternative it beat.

## Tasks come from one real app, at a pinned commit

All eleven tasks are cut from [kezek](https://github.com/midat-fx/kezek) at
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
| Existing behaviour at the pinned commit | t01, t02, t03, t07, t08, t09, t10, t11 | the pinned code as is; the issue describes a real gap |
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
repeatedly and writes the catch rate to `results/flake/`. Each of the three
was caught 5/5 times, and the reference fixes for t05 and t08 passed 5/5.
Six racers over eight rounds make a miss need every round to serialise by
luck. Five runs per variant rules out a coin flip, not a rare miss.

### Mutants attack the verifiers without my imagination in the loop

Known-bad patches only test the wrong fixes I thought of. `harness.cli mutants`
takes each reference fix and drops one hunk at a time (`harness/mutants.py`,
stdlib only), so each mutant is a partial fix picked by the diff, not by me.

- **Hunks, not lines or AST operators.** A reference fix is already a list of
  separate requirements, and a hunk is close to one of them. Dropping one is
  a mistake an agent really makes: it forgot a place. Operator mutation would
  need a TypeScript parser and thousands of gradings at about 20 s each.
- **Only `src/` and `drizzle/`.** A test file can't change what the app does,
  so grading its hunks would only add easy survivors. That skips one hunk.
- **Line numbers are fixed up.** Dropping a hunk moves everything after it in
  that file, and `git apply` starts its search at the new-side line number. In
  repetitive code a stale number could land a hunk in the wrong place, so later
  hunks are renumbered.
- **A build failure isn't a kill.** It's reported as "didn't build" and left
  out of the kill rate, since `tsc` caught it and no verifier ran. Counting
  those would turn 34/37 into 52/55, a better number that says less. A mutant
  that doesn't apply is reported as invalid, not as a kill; none did.
- **Survivors are classified by hand**, in
  `results/mutants/classification.json`: redundant or gap. Whether a hunk matters
  is a judgement about the issue, and writing it down makes it reviewable.

The first pass found two gaps, t07's `toggleService` replay and t10's loading
state. Neither was in my known-bad list, and neither had let a wrong agent patch
through. The t08 survivor is the case I left alone on purpose: without the hunk,
a no-op still publishes a calendar refresh. Rejecting that would be overfitting
to the reference, because the issue doesn't forbid it, nothing changes for a
user, and my alternative fix behaves the same way.

The limits are what you'd expect. A mutant only removes code, so this says
nothing about a fix that's present but wrong; the known-bad patches still cover
that. Only the reference fix is mutated, and race mutants are graded once, so
for those a single rejection is the whole measurement. Dropping two hunks
together isn't tried.

### t11 runs the outbox workers too

t11 ("No thanks" on a waitlist offer) is the first task where the behaviour
happens outside the request: the next client hears about the time through the
outbox, which `pnpm worker` drains. The spec starts two workers itself, with
the command from the candidate's own `package.json`, next to the two app
servers that `task.json` asks for. The checks then read what a client would
get, the SMS in `message_log`, and claim the slot through that SMS's link. A
fix that offers the time to the next client but leaves the declined client's
Redis hold in place fails here: the worker can't hold a time that's still held.

I also wrote a fifth bad patch and dropped it. It declines check-then-act
(read the status, then update) and offers the time in-process. Two declines
that both read "offered" could each release a hold, and the second release
could delete the hold the first one just placed for the next client. It passed
the verifier: six concurrent declines across two servers all read and release
before any offer exists, and that ordering hides the bug. A patch that the
verifier can't fail doesn't belong in `bad/`. The reference fix doesn't have
this problem because the status check is part of the `UPDATE`.

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
- CI keeps the image's layers in the GitHub Actions cache (buildx,
  `type=gha`). I expected that to be the big win and it wasn't: an uncached
  build took 77 s of a 27-minute run, and the 71 gradings are the rest. The
  cache still skips the kezek clone and both `pnpm install`s, which is the part
  that can break on someone else's outage.
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

It works in the other direction too. The judge's only false accept is a
mutant: the wizard shows "Loading…" in two places, and the patch darkens just
one of them. It passed that patch, and my t10 verifier had passed it as well
until the mutant run. A skim of a diff doesn't see what the diff left out.

## Known limitations

- Eleven tasks from one app: good for depth, says nothing about other stacks.
- t11 can't tell a check-then-act decline from a correct one (see above), and
  it can't catch a fix that releases the hold just after committing the
  hand-over rather than before: the worker would have to poll inside that
  millisecond. t11 has no agent runs yet.
- Agent sandboxing on the host is audited, not enforced.
- Mutants only drop one hunk of the reference fix at a time: a survivor-free
  task can still miss a wrong fix that adds code.
- Race verifiers are probabilistic: 5/5 catches per known-bad patch is the
  whole measurement.
- t04 can't trigger the abort-then-cancel race described above
  deterministically, so a fix with that bug would still pass.
- Each grading builds the app from scratch: 28 s median and 81 s p90 over
  197 published gradings (`results/timing.json`), on a loaded shared machine.
  Fine for hundreds of runs, slow for thousands.
