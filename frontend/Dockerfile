# Production multi-stage build for SvelteKit (Node adapter).
# Stage 1: install deps + build.
# Stage 2: minimal runtime with only the built output.

FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# ---- Runtime stage ----
FROM node:22-alpine AS runtime
WORKDIR /app

# Non-root user
RUN addgroup -g 1001 -S sveltekit && adduser -u 1001 -S sveltekit -G sveltekit

# SvelteKit Node adapter output
COPY --from=builder --chown=sveltekit:sveltekit /app/build ./build
COPY --from=builder --chown=sveltekit:sveltekit /app/node_modules ./node_modules
COPY --from=builder --chown=sveltekit:sveltekit /app/package.json .

USER sveltekit

EXPOSE 3001

# NODE_ENV=production disables source maps and enables performance optimisations
ENV NODE_ENV=production PORT=3001
CMD ["node", "build"]
