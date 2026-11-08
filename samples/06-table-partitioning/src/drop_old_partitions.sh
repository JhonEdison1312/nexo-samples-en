#!/bin/bash
# drop_old_partitions.sh - I-2: invoker of fn_drop_old_partitions (retention).
# Without this cron the function existed but nobody called it — biometric_events and
# audits grew forever. Runs monthly via crontab.
# Retention: NEXO_PARTITION_RETENTION_MONTHS (default 24).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../logs/partition_retention.log"
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date -Iseconds)] $1" | tee -a "$LOG_FILE"; }

if [ -z "${DATABASE_URL:-}" ] && [ -f "${SCRIPT_DIR}/../.env" ]; then
    export $(grep -v '^#' "${SCRIPT_DIR}/../.env" | xargs)
fi
ADMIN_DSN="${ADMIN_DATABASE_URL:-${DATABASE_URL:-}}"
if [ -z "$ADMIN_DSN" ]; then
    log "ERROR: ADMIN_DATABASE_URL/DATABASE_URL is not configured"; exit 1
fi

RETENTION="${NEXO_PARTITION_RETENTION_MONTHS:-24}"
DROPPED=$(psql "$ADMIN_DSN" -t -c "SELECT fn_drop_old_partitions(${RETENTION});" 2>&1 | xargs)
log "Retention ${RETENTION} months — partitions dropped: ${DROPPED}"

