# Re-gradings

Every agent patch is graded once when its run ends. A patch is re-graded only
when the verifier, not the patch, was shown to be wrong; each case is listed
here. Re-grading never re-runs the agent.

## 2026-11-01: two false negatives from brittle selectors (wave 1)

| Run | First verdict | Why it failed | Fix | Verdict now |
|---|---|---|---|---|
| sonnet/t09-booking-note/a1 | fail | The patch gave the name field a real `<label>` and dropped its placeholder; the verifier found the field by `getByPlaceholder("Name")`. | `nameField()` / `phoneField()` in `verify/lib/kz.ts`: label first, placeholder as fallback (t01, t02, t09). | pass |
| haiku/t10-wizard-a11y/a1 | fail | The patch put a decorative `aria-hidden` check mark before each service name; the verifier matched button text with `^Men's haircut`. | t10 finds choices by role and accessible name (`button`, `radio` or `option`), which excludes `aria-hidden` content. | pass |

Both were found by reading the failing traces, not by the self-check: the
reference and alternative fixes happened to keep the placeholders and plain
button text. After the fix the full self-check was re-run for t01, t02, t09
and t10 and every agent patch for those tasks was re-graded.

## 2026-11-01: one run lost to a harness incident

`haiku/t03-default-date-tz/a1` was started, but its output directory was
moved away mid-run (a `git stash -u` in the benchmark checkout), so its
transcript was lost. The run is in `ledger.jsonl` twice: the lost invocation
and the re-run that produced the published result.
