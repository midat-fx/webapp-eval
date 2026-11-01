# webapp-eval

A small benchmark of full-stack web tasks for coding agents, where the
grade comes from a browser and a database, not from unit tests.

Ten tasks are cut from [kezek](https://github.com/midat-fx/kezek), a real
Next.js 16 + PostgreSQL + Redis booking app, at a pinned commit. Each task is
an issue as a user would file it, plus a reference patch. The hidden
verifiers build the candidate's version of the app in a container with no
network, drive it with Playwright, check PostgreSQL invariants after the
scenario, and run axe-core on the UI it touches.

## Results

Every number here is computed by `python3 -m harness.report` from files in
[`results/`](results/) ([`results/summary.json`](results/summary.json)).

**Verifiers: 63/63 self-check variants graded as expected**
([`results/selfcheck/`](results/selfcheck/summary.json)). All ten start states
fail, all ten reference and ten alternative fixes pass, and 33/33 known-bad
patches are rejected.

**Agents: 49/49 graded runs pass** (Claude Code headless, `claude -p`,
[`results/agent/`](results/agent/)):

| Task | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| t01-phone-format | 3/3 | 2/2 |
| t02-stale-slots | 3/3 | 2/2 |
| t03-default-date-tz | 3/3 | 2/2 |
| t04-sse-subscriber-leak | 3/3 | 2/2 |
| t05-overlap-race | 3/3 | 2/2 |
| t06-dst-slots | 3/3 | 2/2 |
| t07-staff-permissions | 3/3 | 2/2 |
| t08-status-transitions | 3/3 | 2/2 |
| t09-booking-note | 3/3 | 2/2 |
| t10-wizard-a11y | 2/2 | 2/2 |
| **total** | **29/29** | **20/20** |
| mean wall time | 87 s | 38 s |
| mean turns | 19.0 | 8.2 |
| mean cost (CLI-reported) | $0.84 | $0.19 |

That's a ceiling. These ten tasks don't separate the two models on pass rate,
only on effort: Haiku takes about 2.3× the turns, 2.3× the time and 4.4× the
cost. Harder tasks are the obvious next step. Some other details:

- 50 of a 60-run budget used ([`ledger.jsonl`](results/agent/ledger.jsonl)):
  49 graded runs plus one lost to a harness incident. The remaining 10 runs
  are not done yet, which is why some cells have 2 attempts.
- 0/49 traces touched anything outside their workdir (`touched_outside_workdir`
  in each `meta.json`).
- Two wave-1 failures turned out to be the verifiers' fault, not the
  agents'. Each one is in [`REGRADES.md`](results/agent/REGRADES.md); no
  agent was ever re-run to improve a score.
- The very first run (`haiku/t01-phone-format/a1`) used a shorter
  disallowed-tools list (`meta.json` records the list for every run).

**LLM judge vs. verifiers** (Sonnet 5.5, issue + diff only, no tools,
[`results/judge/sonnet/`](results/judge/sonnet/summary.json)):

| Patches | n | agreement | false accepts | false rejects |
|---|---|---|---|---|
| reference + alternative fixes | 20 | 19/20 | – | 1 |
| known-bad patches | 33 | 33/33 | 0 | – |
| agent patches | 49 | 47/49 | – | 2 |
| **all** | **102** | **97.1 %, κ = 0.93** | **0** | **3** |

The judge never accepted a wrong patch, but it couldn't be tested against an
agent's wrong patch, because there weren't any. Its three false rejects all
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
harness/         grade, selfcheck, flake, agent, judge, report (stdlib Python)
results/         every number in this README, with per-run traces
```
