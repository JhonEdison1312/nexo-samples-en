#!/bin/bash
# ADDED FOR THIS SAMPLE
# Start user-space environment: PostgreSQL, PgBouncer, Redis
# Loads every harness schema AND the extracted src SQL idempotently
# Usage: up.sh [--docker]   (--docker also starts the per-sample Docker route)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# PostgreSQL client/server binaries (Ubuntu/Debian layout) may not be on PATH
# for non-root users; add the newest versioned bin dir if present.
for _pgbin in /usr/lib/postgresql/*/bin; do
    [ -d "$_pgbin" ] && export PATH="$PATH:$_pgbin"
done

PGDATA="/tmp/nexo-pgdata"
PGPORT=15432
PGBOUNCER_PORT=16432
REDIS_PORT=16379
export PGDATA PGPORT

log() { echo "[up] $*"; }

echo "=== Starting NEXO Samples Environment ==="

# ---------------------------------------------------------------- native ----
start_postgres() {
    if pg_isready -h /tmp -p "$PGPORT" >/dev/null 2>&1; then
        log "PostgreSQL already running on /tmp:$PGPORT"
        return
    fi
    log "Starting PostgreSQL on /tmp:$PGPORT ..."
    mkdir -p "$PGDATA"
    if [ ! -f "$PGDATA/PG_VERSION" ]; then
        initdb -D "$PGDATA" --no-locale --encoding=UTF8 >/dev/null
        # pg_hba.conf owns host/local auth lines; postgresql.conf gets only
        # server parameters. Writing auth lines into postgresql.conf makes
        # PostgreSQL fail with "unrecognized configuration parameter".
        {
            echo "host all all 127.0.0.1/32 trust"
            echo "host all all ::1/128 trust"
            echo "local all all trust"
        } > "$PGDATA/pg_hba.conf"
        {
            echo "port = $PGPORT"
            echo "listen_addresses = 'localhost'"
            echo "unix_socket_directories = '/tmp'"
        } >> "$PGDATA/postgresql.conf"
    else
        # Repair older data dirs where auth lines were appended to
        # postgresql.conf (invalid there) instead of pg_hba.conf.
        if grep -qE '^(host|local)\s+all\s+all' "$PGDATA/postgresql.conf"; then
            log "Repairing postgresql.conf/pg_hba.conf split"
            grep -vE '^(host|local)\s+all\s+all' "$PGDATA/postgresql.conf" \
                > "$PGDATA/postgresql.conf.fixed"
            mv "$PGDATA/postgresql.conf.fixed" "$PGDATA/postgresql.conf"
        fi
        grep -qE '^host\s+all\s+all\s+127\.0\.0\.1/32\s+trust' "$PGDATA/pg_hba.conf" \
            || {
                {
                    echo "host all all 127.0.0.1/32 trust"
                    echo "host all all ::1/128 trust"
                    echo "local all all trust"
                } >> "$PGDATA/pg_hba.conf"
            }
    fi
    pg_ctl -D "$PGDATA" -l /tmp/nexo-pg.log -w start
    for _ in $(seq 1 30); do
        pg_isready -h /tmp -p "$PGPORT" >/dev/null 2>&1 && break
        sleep 1
    done
    pg_isready -h /tmp -p "$PGPORT" >/dev/null

    psql -h /tmp -p "$PGPORT" -d postgres -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexo_admin') THEN
        CREATE ROLE nexo_admin LOGIN SUPERUSER;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexo_app') THEN
        CREATE ROLE nexo_app LOGIN PASSWORD 'nexo_secret' NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;
SQL
    psql -h /tmp -p "$PGPORT" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='nexo'" \
        | grep -q 1 || psql -h /tmp -p "$PGPORT" -d postgres -c "CREATE DATABASE nexo OWNER nexo_admin"
    log "PostgreSQL ready: socket /tmp, TCP 127.0.0.1:$PGPORT, db nexo"
}

start_pgbouncer() {
    if pg_isready -h 127.0.0.1 -p "$PGBOUNCER_PORT" >/dev/null 2>&1; then
        log "PgBouncer already running on 127.0.0.1:$PGBOUNCER_PORT"
        return
    fi
    log "Starting PgBouncer on 127.0.0.1:$PGBOUNCER_PORT ..."
    mkdir -p /tmp/nexo-pgbouncer
    cat > /tmp/nexo-pgbouncer/pgbouncer.ini <<EOF
[databases]
nexo = host=/tmp port=$PGPORT dbname=nexo

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = $PGBOUNCER_PORT
unix_socket_dir = /tmp
auth_type = trust
pool_mode = transaction
default_pool_size = 1
max_client_conn = 50
pidfile = /tmp/nexo-pgbouncer/pgbouncer.pid
logfile = /tmp/nexo-pgbouncer/pgbouncer.log
auth_file = /tmp/nexo-pgbouncer/userlist.txt
EOF
    printf '"nexo_app"\n"nexo_admin"\n' > /tmp/nexo-pgbouncer/userlist.txt
    pgbouncer -d /tmp/nexo-pgbouncer/pgbouncer.ini
    for _ in $(seq 1 30); do
        pg_isready -h 127.0.0.1 -p "$PGBOUNCER_PORT" >/dev/null 2>&1 && break
        sleep 1
    done
    pg_isready -h 127.0.0.1 -p "$PGBOUNCER_PORT" >/dev/null
    log "PgBouncer ready (transaction pooling, pool_size=1)"
}

start_redis() {
    if redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
        log "Redis already running on 127.0.0.1:$REDIS_PORT"
        return
    fi
    log "Starting Redis on 127.0.0.1:$REDIS_PORT ..."
    redis-server --port "$REDIS_PORT" --bind 127.0.0.1 --daemonize yes \
        --dir /tmp --save '' --appendonly no --pidfile /tmp/nexo-redis.pid \
        --logfile /tmp/nexo-redis.log
    for _ in $(seq 1 30); do
        redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1 && break
        sleep 1
    done
    redis-cli -p "$REDIS_PORT" ping >/dev/null
    log "Redis ready"
}

# ------------------------------------------------------------- schemas -----
load_sql() {
    local file="$1"
    log "Loading $file"
    psql -h /tmp -p "$PGPORT" -U nexo_admin -d nexo -v ON_ERROR_STOP=1 -q -f "$file"
}

load_schemas() {
    log "Loading harness schemas and extracted SQL (idempotent)..."
    for init_file in samples/*/harness/init.sql; do
        [ -f "$init_file" ] && load_sql "$init_file"
    done
    [ -f samples/01-rls-pgbouncer/src/rls_policies.sql ] \
        && load_sql samples/01-rls-pgbouncer/src/rls_policies.sql
    [ -f samples/02-audit-chain/src/audit_chain_trigger.sql ] \
        && load_sql samples/02-audit-chain/src/audit_chain_trigger.sql
    [ -f samples/06-table-partitioning/src/fn_drop_old_partitions.sql ] \
        && load_sql samples/06-table-partitioning/src/fn_drop_old_partitions.sql
    log "Schemas loaded"
}

# ---------------------------------------------------------------- docker ---
start_docker() {
    command -v docker >/dev/null 2>&1 || { log "docker not available, skipping Docker route"; return; }
    docker info >/dev/null 2>&1 || { log "docker daemon not reachable, skipping Docker route"; return; }
    log "Starting Docker route (per-sample compose files, distinct names/ports)..."
    for harness in samples/01-rls-pgbouncer/harness \
                   samples/02-audit-chain/harness \
                   samples/03-edge-pipeline/harness; do
        if [ -f "$harness/docker-compose.yml" ]; then
            log "  docker compose up -d in $harness"
            (cd "$harness" && docker compose up -d --build)
        fi
    done
}

start_postgres
start_pgbouncer
start_redis
load_schemas
[ "${1:-}" = "--docker" ] && start_docker

echo "=== Environment started: PG /tmp+127.0.0.1:$PGPORT, PgBouncer 127.0.0.1:$PGBOUNCER_PORT, Redis 127.0.0.1:$REDIS_PORT ==="
