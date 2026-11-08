#!/bin/bash
# create_monthly_partition.sh - Creates monthly partitions for the 8 partitioned
# tables of NEXO. Usage: ./create_monthly_partition.sh [YYYY-MM] [table]
# Without arguments creates the next month partition in ALL tables.
# I-2: previously only covered biometric_events — the other 7 accumulated everything in their
# DEFAULT partition (no pruning possible and outside retention scope).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../logs/partition_creation.log"
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date -Iseconds)] $1" | tee -a "$LOG_FILE"; }

if [ -z "${DATABASE_URL:-}" ] && [ -f "${SCRIPT_DIR}/../.env" ]; then
    export $(grep -v '^#' "${SCRIPT_DIR}/../.env" | xargs)
fi
# SEC-2: administrative DDL — requires ADMIN_DATABASE_URL (role with DDL);
# DATABASE_URL only in legacy single-role deployments.
ADMIN_DSN="${ADMIN_DATABASE_URL:-${DATABASE_URL:-}}"
if [ -z "$ADMIN_DSN" ]; then
    log "ERROR: ADMIN_DATABASE_URL/DATABASE_URL is not configured"; exit 1
fi

# table:range_column — the 8 partitioned parents in the schema
declare -A PARTS=(
    [biometric_events]=event_timestamp
    [attendance_incidents]=detected_at
    [internal_messages]=sent_at
    [twilio_messages]=sent_at
    [user_commands]=executed_at
    [sos_alerts]=emitted_at
    [student_record_audit]=performed_at
    [global_audit_logs]=created_at
)

TARGET_MONTH="${1:-$(date -d "+1 month" +%Y-%m)}"
ONLY_TABLE="${2:-}"
YEAR="${TARGET_MONTH:0:4}"; MONTH="${TARGET_MONTH:5:2}"
P_START="${YEAR}-${MONTH}-01"
P_END=$(date -d "${P_START} +1 month" +%Y-%m-%d)

fail=0
for TBL in "${!PARTS[@]}"; do
    [ -n "$ONLY_TABLE" ] && [ "$ONLY_TABLE" != "$TBL" ] && continue
    PNAME="${TBL}_${YEAR}_${MONTH}"
    EXISTS=$(psql "$ADMIN_DSN" -t -c "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='${PNAME}' AND n.nspname='public');" 2>&1 | xargs)
    if [ "$EXISTS" = "t" ]; then
        log "Partition ${PNAME} already exists."
        continue
    fi
    if psql "$ADMIN_DSN" -c "CREATE TABLE IF NOT EXISTS ${PNAME} PARTITION OF ${TBL} FOR VALUES FROM ('${P_START}') TO ('${P_END}');" >>"$LOG_FILE" 2>&1; then
        log "Partition ${PNAME} created [${P_START}, ${P_END})."
    else
        log "ERROR: failed to create ${PNAME}"; fail=1
    fi
done
exit $fail
