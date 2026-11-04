# webapp-eval

A small benchmark of full-stack web tasks for coding agents, where the
grade comes from a browser and a database, not from unit tests.

Eleven tasks are cut from [kezek](https://github.com/midat-fx/kezek), a real
Next.js 16 + PostgreSQL + Redis booking app, at a pinned commit. Each task is
an issue as a user would file it, plus a reference patch. The hidden
verifiers build the candidate's version of the app in a container with no
network, drive it with Playwright, check PostgreSQL invariants after the
scenario, and run axe-core on the UI it touches.

## Results

Every number here is computed by `python3 -m harness.report` from files in
[`results/`](results/) ([`results/summary.json`](results/summary.json)).

**Verifiers: 71/71 self-check variants graded as expected**
([`results/selfcheck/`](results/selfcheck/summary.json)). All eleven start states
fail, all eleven reference and eleven alternative fixes pass, and 38/38 known-bad
patches are rejected.

**Agents: 59/59 graded runs pass** (Claude Code headless, `claude -p`,
[`results/agent/`](results/agent/)):

| Task | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| t01-phone-format | 3/3 | 3/3 |
| t02-stale-slots | 3/3 | 3/3 |
| t03-default-date-tz | 3/3 | 3/3 |
| t04-sse-subscriber-leak | 3/3 | 3/3 |
| t05-overlap-race | 3/3 | 3/3 |
| t06-dst-slots | 3/3 | 3/3 |
| t07-staff-permissions | 3/3 | 3/3 |
| t08-status-transitions | 3/3 | 3/3 |
| t09-booking-note | 3/3 | 3/3 |
| t10-wizard-a11y | 3/3 | 2/2 |
| **total** | **30/30** | **29/29** |
| mean wall time | 87 s | 41 s |
| mean turns | 18.7 | 8.0 |
| mean cost (CLI-reported) | $0.84 | $0.20 |

That's a ceiling. These ten tasks don't separate the two models on pass rate,
only on effort: Haiku takes about 2.3× the turns, 2.1× the time and 4.2× the
cost. Harder tasks are the obvious next step, and t11 is the first: a feature
that spans the offer page, the waitlist code, Redis holds and the outbox
workers. It came after the 60-run budget was spent, so no agent has run on it
yet and it isn't in the table. Some other details:

- The whole 60-run budget is used ([`ledger.jsonl`](results/agent/ledger.jsonl)):
  59 graded runs plus one lost to a harness incident. That lost run is why
  Sonnet has only two attempts on t10: its third attempt would have been run 61.
- 0/59 traces touched anything outside their workdir (`touched_outside_workdir`
  in each `meta.json`).
- Two wave-1 failures turned out to be the verifiers' fault, not the
  agents'. Each one is in [`REGRADES.md`](results/agent/REGRADES.md); no
  agent was ever re-run to improve a score.
- The very first run (`haiku/t01-phone-format/a1`) used a shorter
  disallowed-tools list (`meta.json` records the list for every run).

**Race verifiers are stable** ([`results/flake/`](results/flake/)). The three
known-bad patches that are wrong only under concurrency were each graded five
more times, and so were the two reference fixes they compete with:

| Variant | Expected | As expected |
|---|---|---|
| t05 check-then-insert | fail | 5/5 |
| t05 in-process lock (two servers) | fail | 5/5 |
| t08 read-then-update | fail | 5/5 |
| t05 reference fix | pass | 5/5 |
| t08 reference fix | pass | 5/5 |

Five runs is enough to show the checks aren't coin flips, not enough to
put a number on a rare miss.

**Verifiers vs. mutants** ([`results/mutants/`](results/mutants/)). A mutant is
a reference fix with one hunk dropped, so it is a partial fix nobody had to
think of. There are 64 hunks; one only touches a test file, which leaves 63
mutants to grade:

| Task | Hunks | Rejected by a verifier | Didn't build | Survived |
|---|---|---|---|---|
| t01-phone-format | 6 | 2 | 4 | 0 |
| t02-stale-slots | 2 | 1 | 1 | 0 |
| t03-default-date-tz | 3 | 2 | 1 | 0 |
| t04-sse-subscriber-leak | 3 | 1 | 1 | 1 |
| t05-overlap-race | 3 | 2 | 1 | 0 |
| t06-dst-slots | 2 | 1 | 0 | 0 |
| t07-staff-permissions | 16 | 11 | 4 | 1 |
| t08-status-transitions | 2 | 0 | 1 | 1 |
| t09-booking-note | 10 | 5 | 5 | 0 |
| t10-wizard-a11y | 9 | 9 | 0 | 0 |
| t11-decline-offer | 8 | 1 | 5 | 2 |
| **total** | **64** | **35** | **23** | **5** |

Of the 40 mutants that built, the verifiers reject 35. The 23 that didn't
build say nothing about the verifiers, so they aren't counted as kills (one of
them is a migration failure, the rest are compile errors). None of the five
survivors breaks a requirement in its issue
([`classification.json`](results/mutants/classification.json)). Two drop only
a comment. One sends a calendar refresh after a no-op, as my alternative fix
does too. The two in t11 only change what the page shows after "No thanks": a
404 or "no longer active" instead of a thank-you. The issue doesn't ask for
either, so I didn't add a check for it.

The first pass had five survivors, and two were real holes in my verifiers,
both on requirements the issue states outright. The t07 replay never submitted
the Hide button of a service, so a fix leaving `toggleService` open to staff
passed. The t10 axe scan never ran while times were loading, so a fix leaving
that "Loading…" low-contrast passed. Both checks exist now, both mutants are
known-bad patches, and all 11 agent patches for those tasks still pass, so no
agent had benefited from either hole. The first verdicts are in
[`results/mutants/superseded/`](results/mutants/superseded/).

**LLM judge vs. verifiers** (Sonnet 5.5, issue + diff only, no tools,
[`results/judge/sonnet/`](results/judge/sonnet/summary.json)):

| Patches | n | agreement | false accepts | false rejects |
|---|---|---|---|---|
| reference + alternative fixes | 22 | 21/22 | – | 1 |
| known-bad patches | 38 | 37/38 | 1 | – |
| agent patches | 59 | 57/59 | – | 2 |
| **all** | **119** | **96.6 %, κ = 0.92** | **1** | **3** |

The judge's one false accept is a mutant: the t10 patch that darkens one
"Loading…" and misses the other. The judge read that as "darkens the Loading
text" and passed it. It also couldn't be tested against an agent's wrong patch,
because there weren't any. Its three false rejects all
come from missing context: it assumed `redisSub` didn't exist because the
diff didn't define it, and twice it guessed that the browser blocks formatted
phone numbers before the API sees them, which the wizard test shows it
doesn't.

The judge's first pass also beat my own verifiers twice. It rejected my
alternative fixes for t09 (the admin card collapsed the note's line breaks)
and t04 (a second cleanup call could unsubscribe a newer tab), and both
times it was right. The t09 verifier now checks the rendered text, and the
old t09 alternative is a known-bad patch. Both alternatives are fixed and
re-judged; the first versions and their verdicts are in
[`results/judge/superseded/`](results/judge/superseded/).


**Grading time** ([`results/timing.json`](results/timing.json)). Wall time
of every published grading that got as far as the checks (builds that failed
stop early and are left out), on a shared Mac whose load ranged from idle to
100+:

| Task | Gradings | p50 | p90 |
|---|---|---|---|
| t01-phone-format | 14 | 26 s | 39 s |
| t02-stale-slots | 13 | 30 s | 36 s |
| t03-default-date-tz | 14 | 47 s | 83 s |
| t04-sse-subscriber-leak | 14 | 30 s | 78 s |
| t05-overlap-race | 30 | 17 s | 51 s |
| t06-dst-slots | 13 | 43 s | 72 s |
| t07-staff-permissions | 26 | 18 s | 38 s |
| t08-status-transitions | 23 | 21 s | 54 s |
| t09-booking-note | 19 | 37 s | 82 s |
| t10-wizard-a11y | 22 | 26 s | 56 s |
| t11-decline-offer | 9 | 185 s | 221 s |
| **all** | **197** | **28 s** | **81 s** |

t11 is slow by design: its checks wait for outbox workers that poll every two
seconds, and all nine of its gradings ran while the machine was at its busiest.

## Tasks

| Task | Kind | What's wrong | Verified by |
|---|---|---|---|
| [t01-phone-format](tasks/t01-phone-format/issue.md) | UI form + API | `+7 (701) 555-12-34` is rejected; must be accepted and stored canonically | wizard + direct API, SQL: one client per number |
| [t02-stale-slots](tasks/t02-stale-slots/issue.md) | UI state | a slow `/slots` response for the previous date overwrites the current grid | Playwright with delayed responses, SQL: booking lands on the selected day |
| [t03-default-date-tz](tasks/t03-default-date-tz/issue.md) | timezone | the wizard opens on the UTC date, not the business's date | wizard in 5 business timezones, visitor in a 6th |
| [t04-sse-subscriber-leak](tasks/t04-sse-subscriber-leak/issue.md) | SSE | every closed admin tab leaves a Redis subscriber and connection behind | Redis `PUBSUB NUMSUB` / `CLIENT LIST` after closing tabs, live update still arrives |
| [t05-overlap-race](tasks/t05-overlap-race/issue.md) | API/DB race | two overlapping confirmed bookings for one master under concurrent checkout | 6 racers × 8 rounds across 2 app servers, SQL: no overlaps |
| [t06-dst-slots](tasks/t06-dst-slots/issue.md) | timezone | wrong opening times on daylight-saving days | slot API on 8 DST days in 2 zones and 2 years, wizard |
| [t07-staff-permissions](tasks/t07-staff-permissions/issue.md) | permissions | staff logins can change prices and manage colleagues | owner-only pages, replayed server-action forms, SQL: nothing changed |
| [t08-status-transitions](tasks/t08-status-transitions/issue.md) | API/DB race | a cancelled booking can be completed later; double clicks double-count | replayed forms, 9 concurrent changes across 2 servers, SQL: one audit entry per booking |
| [t09-booking-note](tasks/t09-booking-note/issue.md) | small feature | let clients leave a note, show it on the calendar | wizard + API limits, axe on the step, XSS check on the calendar |
| [t10-wizard-a11y](tasks/t10-wizard-a11y/issue.md) | UI accessibility | unlabelled fields, low contrast, silent errors, selection only by colour | axe on every wizard state, live regions, ARIA selection state |
| [t11-decline-offer](tasks/t11-decline-offer/issue.md) | feature across processes | a waitlist offer can't be turned down; the time sits on hold for 15 minutes | 2 app servers + 2 outbox workers: next client's SMS, slot back on sale, 6 concurrent declines, decline after claim; SQL: one live offer per time |

## How grading works

```
candidate.patch ──► docker run --network none webapp-eval-runner
                     ├─ git apply  setup.patch + candidate.patch
                     ├─ next build                       (fail → build_failed)
                     ├─ postgres 16 + redis, migrate, seed
                     ├─ next start ×1 or ×2 (race tasks)
                     ├─ playwright test  (hidden specs, copied in after the build)
                     ├─ SQL invariants   (verify/invariants.sql)
                     └─ result.json + trace.jsonl
```

A task passes only if every check passes. Changing `package.json` or the
lockfile fails the grading: there is no network to install anything.

**The verifiers are tested too.** For every task the self-check grades the
untouched start state (must fail), the reference fix and an independently
written alternative fix (must pass), and three to five known-bad patches that
an agent could plausibly write (must fail): partial fixes, UI-only fixes,
fixes that hard-code the issue's own example, and fixes at the wrong layer —
an in-process mutex where there are two servers, a unique index where the
problem is overlap. CI runs the whole matrix on every push.

Design decisions and their alternatives are in [docs/DESIGN.md](docs/DESIGN.md).

## Run it

```bash
make test            # harness unit tests + build image + verifier self-check
```

Needs Docker and Python 3.10+; nothing else is installed on the host. The
image clones kezek at the pinned commit. On a machine where `docker` can't
pull with the default credential helper, point `DOCKER_CONFIG` at a config
without `credsStore`.

```bash
python3 -m harness.cli grade t05-overlap-race my.patch     # grade one patch
python3 -m harness.cli agent t01-phone-format --models haiku --attempts 1
python3 -m harness.cli judge --model sonnet
python3 -m harness.cli mutants t07-staff-permissions -j 2  # reference fix minus one hunk at a time
python3 -m harness.report                                  # tables below, from results/
```

Agent runs need the `claude` CLI logged in; see DESIGN.md for how they are
isolated and audited.

## Layout

```
base/            pinned kezek SHA + offline patch (no Google Fonts at build time)
tasks/<id>/      issue.md, setup.patch, solution.patch, alt.patch, bad/*.patch, verify/
verify/          verifier toolchain: Playwright config, shared helpers, axe, SQL runner
docker/          grading image and the in-container grading script
harness/         grade, selfcheck, flake, mutants, agent, judge, report (stdlib Python)
results/         every number in this README, with per-run traces
```

## How it was built

The code, tests and this README were written by Claude Code, Anthropic's AI coding agent, working to Midat's problem statement: Midat chose the problem, set the requirements, reviewed the work and accepted it. Every number above comes from the files in this repository and the commands that produced them.
