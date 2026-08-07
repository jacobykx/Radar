# syntax=docker/dockerfile:1

# ── dependencies ───────────────────────────────────────────────────────────────
FROM node:22-slim AS deps

WORKDIR /app

# `npm ci` installs exactly the lockfile, so a build is reproducible.
COPY package.json package-lock.json ./
RUN npm ci

# ── builder ────────────────────────────────────────────────────────────────────
FROM node:22-slim AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Baked in at build time because Next inlines NEXT_PUBLIC_* into the client bundle. A
# different backend URL therefore means a different image -- pass it per environment.
ARG NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}

RUN npm run build

# ── runtime ────────────────────────────────────────────────────────────────────
FROM node:22-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN useradd --create-home --uid 10001 iap

COPY --chown=iap:iap package.json package-lock.json next.config.mjs ./

# Production dependencies only -- the builder's node_modules carries jest, typescript and
# the rest of the dev toolchain, none of which belongs in a runtime image.
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=builder --chown=iap:iap /app/.next ./.next

USER iap

EXPOSE 3010

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3010').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["npm", "run", "start"]
