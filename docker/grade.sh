#!/usr/bin/env bash
# Grades one candidate patch for one task, inside a `--network none` container.
#   /task             task directory (read-only): task.json, setup.patch, verify/
#   /candidate.patch  the patch under test, relative to the task's start state
#   /out              writable: trace.jsonl, result.json, logs
set -uo pipefail
APP=/opt/kezek
OUT=/out
TRACE=$OUT/trace.jsonl
: >"$TRACE"

ev() { # ev <step> <status> [detail]  -> one JSONL trace line
  node -e 'const [s,st,d]=process.argv.slice(1);console.log(JSON.stringify({ts:new Date().toISOString(),step:s,status:st,detail:d||undefined}))' \
    "$1" "$2" "${3:-}" >>"$TRACE"
}
finish() { # finish <verdict> <reason>
  node /opt/verify/lib/result.mjs "$1" "$2" >"$OUT/result.json"
  ev done "$1" "$2"
  exit 0
}

cd "$APP" || exit 1
ev start ok "$(node -p 'require("/task/task.json").id')"

if [ -s /task/setup.patch ]; then
  git apply --whitespace=nowarn /task/setup.patch || { ev setup fail; finish error setup_patch_failed; }
fi
ev setup ok

if [ -s /candidate.patch ]; then
  if ! git apply --whitespace=nowarn /candidate.patch 2>"$OUT/apply.log"; then
    ev apply fail "$(head -c 500 "$OUT/apply.log")"
    finish fail patch_does_not_apply
  fi
fi
ev apply ok "$(git status --porcelain | wc -l) files touched"

# Lockfile drift would mean new dependencies; there is no network to fetch them.
if ! git diff --quiet HEAD -- package.json pnpm-lock.yaml 2>/dev/null; then
  ev deps fail "package.json or lockfile changed"
  finish fail dependencies_changed
fi

export DATABASE_URL=postgres://kezek:kezek@127.0.0.1:5432/kezek
export REDIS_URL=redis://127.0.0.1:6379
export SESSION_SECRET=webapp-eval
export NODE_ENV=production

if ! timeout 900 ./node_modules/.bin/next build >"$OUT/build.log" 2>&1; then
  ev build fail "$(tail -c 800 "$OUT/build.log")"
  finish fail build_failed
fi
ev build ok

# Services: fresh cluster every grading, nothing survives between candidates.
pg_ctlcluster 16 main start >/dev/null 2>&1 || { ev postgres fail; finish error postgres_failed; }
su postgres -c "psql -q -c \"CREATE ROLE kezek LOGIN SUPERUSER PASSWORD 'kezek'\" -c 'CREATE DATABASE kezek OWNER kezek'" >/dev/null
redis-server --daemonize yes --save '' --appendonly no >/dev/null
ev services ok

if ! ./node_modules/.bin/drizzle-kit migrate >"$OUT/migrate.log" 2>&1; then
  ev migrate fail "$(tail -c 800 "$OUT/migrate.log")"
  finish fail migrate_failed
fi
if ! ./node_modules/.bin/tsx src/db/seed.ts >"$OUT/seed.log" 2>&1; then
  ev seed fail "$(tail -c 800 "$OUT/seed.log")"
  finish fail seed_failed
fi
ev seed ok

INSTANCES=$(node -p 'require("/task/task.json").instances ?? 1')
for i in $(seq 1 "$INSTANCES"); do
  port=$((2999 + i))
  PORT=$port nohup ./node_modules/.bin/next start -p "$port" >"$OUT/server-$port.log" 2>&1 &
done
for i in $(seq 1 "$INSTANCES"); do
  port=$((2999 + i))
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null "http://127.0.0.1:$port/login" && break
    sleep 1
  done
  curl -sf -o /dev/null "http://127.0.0.1:$port/login" || { ev server fail "port $port"; finish fail server_not_ready; }
done
ev server ok "$INSTANCES instance(s)"

# Verifiers are copied in only now, after the candidate's code is built.
mkdir -p /opt/verify/specs
cp /task/verify/*.spec.ts /opt/verify/specs/ 2>/dev/null
cd /opt/verify
if ls specs/*.spec.ts >/dev/null 2>&1; then
  PW_JSON=$OUT/playwright.json ./node_modules/.bin/playwright test >"$OUT/playwright.log" 2>&1
  ev playwright "exit:$?"
fi
if [ -f /task/verify/invariants.sql ]; then
  node lib/invariants.mjs /task/verify/invariants.sql >"$OUT/invariants.json" 2>"$OUT/invariants.log"
  ev invariants "exit:$?"
fi
finish auto checks
