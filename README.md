# webapp-eval

A small benchmark of full-stack web tasks for coding agents, where the
grade comes from a browser and a database, not from unit tests.

Ten tasks are cut from [kezek](https://github.com/midat-fx/kezek), a real
Next.js 16 + PostgreSQL + Redis booking app, at a pinned commit. Each task is
an issue as a user would file it, plus a reference patch. The hidden
verifiers build the candidate's version of the app in a container with no
network, drive it with Playwright, check PostgreSQL invariants after the
scenario, and run axe-core on the UI it touches.

<!-- RESULTS -->

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
written alternative fix (must pass), and two to four known-bad patches that
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
