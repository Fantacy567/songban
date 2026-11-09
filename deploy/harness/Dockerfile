# Fixed upstream source; no npm floating Harness release.
FROM node:24.11.0-bookworm
LABEL org.opencontainers.image.source="https://github.com/deepseek-ai/deepseek-harness"
LABEL org.opencontainers.image.revision="ce7073d51254c26cd63b22a60835b8f948deb447"
LABEL org.songban.harness.contract="2026-11-03-files-v1"
WORKDIR /opt/harness
RUN git init . && git remote add origin https://github.com/deepseek-ai/deepseek-harness.git && git fetch --depth 1 origin ce7073d51254c26cd63b22a60835b8f948deb447 && git checkout --detach FETCH_HEAD && test "$(git rev-parse HEAD)" = "ce7073d51254c26cd63b22a60835b8f948deb447"
RUN corepack enable && corepack prepare pnpm@11.28.5 --activate && pnpm install --frozen-lockfile && pnpm run build
COPY worker.mjs /opt/harness/songban-worker.mjs
COPY profile.mjs file-guard.mjs /opt/harness/
WORKDIR /work
USER 1000:1000
ENV HOME=/tmp DSH_HOME=/tmp/dsh
ENTRYPOINT ["node", "/opt/harness/songban-worker.mjs"]
