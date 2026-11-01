# One image holds everything a grading needs: the app under test, Postgres,
# Redis, and a headless Chromium. Gradings run with `--network none`, so the
# only network a candidate patch ever sees is the container's loopback.
FROM node:24-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    NEXT_TELEMETRY_DISABLED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git gnupg postgresql-common redis-server \
 && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
 && apt-get install -y --no-install-recommends postgresql-16 \
 && rm -rf /var/lib/apt/lists/*

RUN corepack enable && corepack prepare pnpm@11.9.0 --activate

# Verifier toolchain (Playwright, axe, pg) lives apart from the app so a
# candidate patch can't change what the verifiers import.
COPY verify/package.json verify/pnpm-lock.yaml /opt/verify/
RUN cd /opt/verify && pnpm install --frozen-lockfile \
 && ./node_modules/.bin/playwright install --with-deps --only-shell chromium \
 && rm -rf /var/lib/apt/lists/* /root/.cache

# The app at the pinned commit, plus the offline patch (no Google Fonts fetch
# at build time). Kept as a git repo so gradings can `git apply` onto it.
ARG KEZEK_SHA
COPY base/offline.patch /tmp/offline.patch
RUN git clone https://github.com/midat-fx/kezek /opt/kezek \
 && cd /opt/kezek && git checkout -q "$KEZEK_SHA" \
 && git -c user.email=eval@localhost -c user.name=eval apply /tmp/offline.patch \
 && git -c user.email=eval@localhost -c user.name=eval commit -qam "webapp-eval: offline base" \
 && pnpm install --frozen-lockfile \
 && rm -rf /root/.cache /root/.local/share/pnpm/store

COPY docker/grade.sh /opt/grade.sh
COPY verify/lib /opt/verify/lib
COPY verify/playwright.config.ts /opt/verify/playwright.config.ts
ENTRYPOINT ["/opt/grade.sh"]
