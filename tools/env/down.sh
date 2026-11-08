#!/bin/bash
# ADDED FOR THIS SAMPLE
# Stop user-space environment: PostgreSQL, PgBouncer, Redis (+ Docker route if present)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "=== Stopping NEXO Samples Environment ==="

# Native Redis
if [ -f /tmp/nexo-redis.pid ] && kill -0 "$(cat /tmp/nexo-redis.pid)" 2>/dev/null; then
    echo "Stopping Redis (pid $(cat /tmp/nexo-redis.pid))"
    redis-cli -p 16379 shutdown nosave 2>/dev/null || kill "$(cat /tmp/nexo-redis.pid)" 2>/dev/null || true
fi

# Native PgBouncer
if [ -f /tmp/nexo-pgbouncer/pgbouncer.pid ] && kill -0 "$(cat /tmp/nexo-pgbouncer/pgbouncer.pid)" 2>/dev/null; then
    echo "Stopping PgBouncer (pid $(cat /tmp/nexo-pgbouncer/pgbouncer.pid))"
    kill "$(cat /tmp/nexo-pgbouncer/pgbouncer.pid)" 2>/dev/null || true
fi

# Native PostgreSQL
if [ -f /tmp/nexo-pgdata/postmaster.pid ]; then
    echo "Stopping PostgreSQL (/tmp/nexo-pgdata)"
    pg_ctl -D /tmp/nexo-pgdata -m fast -w stop || true
fi

# Docker route (idempotent: compose down is a no-op when nothing is running)
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    for harness in samples/*/harness; do
        if [ -f "$harness/docker-compose.yml" ]; then
            echo "Stopping docker compose project in $harness"
            (cd "$harness" && docker compose down -v)
        fi
    done
fi

echo "=== Environment stopped ==="
