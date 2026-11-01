// Folds the Playwright JSON report and the SQL invariant results into one
// verdict. A task passes only if every check ran and every check passed.
import { existsSync, readFileSync } from "node:fs";

const [verdictArg, reason] = process.argv.slice(2);
const out = "/out";
const checks = [];

function walk(suite, file) {
  for (const s of suite.suites ?? []) walk(s, file ?? s.file);
  for (const spec of suite.specs ?? []) {
    for (const t of spec.tests ?? []) {
      const last = t.results?.at(-1);
      const tags = [...(spec.tags ?? []), ...(t.tags ?? [])];
      checks.push({
        kind: tags.includes("axe") || tags.includes("@axe") ? "axe" : "playwright",
        name: spec.title,
        pass: t.status === "expected",
        detail: last?.error?.message?.slice(0, 600),
      });
    }
  }
}

if (existsSync(`${out}/playwright.json`)) {
  const report = JSON.parse(readFileSync(`${out}/playwright.json`, "utf8"));
  for (const s of report.suites ?? []) walk(s, s.file);
  for (const e of report.errors ?? []) {
    checks.push({ kind: "playwright", name: "load", pass: false, detail: e.message?.slice(0, 600) });
  }
}
if (existsSync(`${out}/invariants.json`)) {
  for (const inv of JSON.parse(readFileSync(`${out}/invariants.json`, "utf8"))) {
    checks.push({ kind: "sql", name: inv.name, pass: inv.pass, detail: inv.detail });
  }
}

let verdict = verdictArg;
if (verdict === "auto") verdict = checks.length > 0 && checks.every((c) => c.pass) ? "pass" : "fail";
console.log(JSON.stringify({ verdict, reason: verdictArg === "auto" ? undefined : reason, checks }, null, 2));
