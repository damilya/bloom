FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
# Deployments: leave NEXT_PUBLIC_API_URL empty (same-origin calls) and set BACKEND_INTERNAL_URL,
# which is baked into the rewrite rules at build time.
ARG NEXT_PUBLIC_API_URL=""
ARG BACKEND_INTERNAL_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
