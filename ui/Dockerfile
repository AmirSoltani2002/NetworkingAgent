FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY ui/package.json ui/package.json
COPY core/package.json core/package.json
RUN npm ci
COPY ui ui
RUN npm run build --workspace ui

FROM nginx:stable-alpine
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/ui/dist /usr/share/nginx/html
EXPOSE 80
