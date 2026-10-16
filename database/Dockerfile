FROM postgres:17-alpine

LABEL org.opencontainers.image.title="Meta-Harness message database"
COPY database/schema.sql /docker-entrypoint-initdb.d/001-chats.sql
