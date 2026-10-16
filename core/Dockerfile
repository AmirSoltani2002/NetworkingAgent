FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY ui/package.json ui/package.json
COPY core/package.json core/package.json
RUN npm ci
COPY core core
RUN npm run build --workspace core

FROM node:24-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
COPY ui/package.json ui/package.json
COPY core/package.json core/package.json
RUN npm ci --omit=dev --workspace core --include-workspace-root=false

FROM node:24-bookworm-slim
ENV NODE_ENV=production CORE_HOST=0.0.0.0 CORE_PORT=8000
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY --from=build /app/core/dist ./core/dist
COPY core/config ./core/config
COPY database/schema.sql ./database/schema.sql
COPY database/migrations ./database/migrations
USER node
EXPOSE 8000
CMD ["node", "core/dist/main.js"]
