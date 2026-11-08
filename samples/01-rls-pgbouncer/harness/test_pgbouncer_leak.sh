#!/usr/bin/env bash
# ADDED FOR THIS SAMPLE
# Test RLS tenant isolation and PgBouncer connection reuse behavior.
# Every check is a real assertion; the banner prints only if all pass.
set -uo pipefail

PGBOUNCER_HOST="${NEXO_PGBOUNCER_HOST:-127.0.0.1}"
PGBOUNCER_PORT="${NEXO_PGBOUNCER_PORT:-16432}"
DB_NAME="${NEXO_DB_NAME:-nexo}"
DB_USER="${NEXO_DB_USER:-nexo_app}"
export PGPASSWORD="${NEXO_DB_PASSWORD:-nexo_secret}"
FAIL=0

run_query() {
    psql -h "${PGBOUNCER_HOST}" -p "${PGBOUNCER_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -A -t "$@"
}

# last_row: quiet mode + tail -n1 so BEGIN/COMMIT/SET tags never pollute
# a count assertion.
last_row() {
    run_query -q "$@" | tail -n1
}

check() { # check <test-name> <actual> <expected>
    local name="$1" actual="$2" expected="$3"
    if [[ "${actual}" == "${expected}" ]]; then
        echo "  [PASS] ${name}"
    else
        echo "  [FAIL] ${name}: expected '${expected}', got '${actual}'"
        FAIL=1
    fi
}

echo "=== 01-RLS-PGBOUNCER VERIFICATION DEMO ==="
echo "Connected through PgBouncer: ${PGBOUNCER_HOST}:${PGBOUNCER_PORT} as role '${DB_USER}'"

echo ""
echo "--- TEST 0: Verify current_user is NOSUPERUSER app role ---"
CURRENT_USER=$(run_query -c "SELECT current_user;")
IS_SUPERUSER=$(run_query -c "SELECT usesuper FROM pg_user WHERE usename = current_user;")
echo "current_user: ${CURRENT_USER}"
echo "is_superuser: ${IS_SUPERUSER}"
check "current_user is nexo_app" "${CURRENT_USER}" "nexo_app"
check "user is NOT superuser" "${IS_SUPERUSER}" "f"

echo ""
echo "--- TEST 1: Session-Level Setting Leaks Across Connections (The Vulnerability) ---"
echo "Client A sets app.current_school_id at session level (without transaction scope):"
run_query -c "SET app.current_school_id = '11111111-1111-1111-1111-111111111111';" >/dev/null
echo "Client A session setting complete."

echo "Client B opens a new connection to PgBouncer and inspects app.current_school_id:"
LEAKED_GUC=$(run_query -c "SELECT COALESCE(current_setting('app.current_school_id', true), '<empty>');")
echo "Client B observed GUC: ${LEAKED_GUC}"
check "session-level GUC leaks across pooled connections" "${LEAKED_GUC}" "11111111-1111-1111-1111-111111111111"

# Reset backend connection state for subsequent tests
run_query -c "RESET app.current_school_id;" >/dev/null 2>&1

echo ""
echo "--- TEST 2: Transaction-Scoped set_config(..., true) / SET LOCAL (The Safe Pattern) ---"
echo "Client A sets app.current_school_id inside a BEGIN/COMMIT block with is_local=true:"
run_query -q <<'SQL' >/dev/null
BEGIN;
SELECT set_config('app.current_school_id', '22222222-2222-2222-2222-222222222222', true);
COMMIT;
SQL
echo "Client A transaction committed."

echo "Client B opens a new connection to PgBouncer and inspects app.current_school_id:"
ISOLATED_GUC=$(run_query -c "SELECT COALESCE(NULLIF(current_setting('app.current_school_id', true), ''), '<empty>');")
echo "Client B observed GUC: ${ISOLATED_GUC}"
check "transaction-scoped GUC does NOT leak" "${ISOLATED_GUC}" "<empty>"

echo ""
echo "--- TEST 3: Row-Level Security Tenant Isolation ---"
echo "Query 3a: Read with no context set:"
NO_CTX_COUNT=$(last_row -c "SELECT count(*) FROM students;")
echo "Visible rows: ${NO_CTX_COUNT}"
check "no-context read returns 0 rows (RLS default-deny)" "${NO_CTX_COUNT}" "0"

echo "Query 3b: Read with School A context ('11111111-1111-1111-1111-111111111111'):"
run_query -q <<'SQL' | tail -n +2
BEGIN;
SELECT set_config('app.current_school_id', '11111111-1111-1111-1111-111111111111', true);
SELECT school_id || ' | ' || first_name || ' ' || last_name FROM students ORDER BY first_name;
COMMIT;
SQL

echo "Query 3c: Attempt cross-tenant read (querying School B while scoped to School A):"
CROSS_COUNT=$(last_row <<'SQL'
BEGIN;
SELECT set_config('app.current_school_id', '11111111-1111-1111-1111-111111111111', true);
SELECT count(*) FROM students WHERE school_id = '22222222-2222-2222-2222-222222222222';
COMMIT;
SQL
)
echo "Cross-tenant rows returned: ${CROSS_COUNT}"
check "cross-tenant read returns 0 rows" "${CROSS_COUNT}" "0"

echo "Query 3d: Read with School B context ('22222222-2222-2222-2222-222222222222'):"
run_query -q <<'SQL' | tail -n +2
BEGIN;
SELECT set_config('app.current_school_id', '22222222-2222-2222-2222-222222222222', true);
SELECT school_id || ' | ' || first_name || ' ' || last_name FROM students ORDER BY first_name;
COMMIT;
SQL

echo ""
echo "--- TEST 4: Empty GUC After COMMIT (Same Connection) ---"
run_query -q <<'SQL'
BEGIN;
SELECT set_config('app.current_school_id', '11111111-1111-1111-1111-111111111111', true);
COMMIT;
SELECT 'GUC value after COMMIT: ' || COALESCE(NULLIF(current_setting('app.current_school_id', true), ''), '<empty>');
SQL

echo ""
if [[ "${FAIL}" -eq 0 ]]; then
    echo "=== 01-RLS-PGBOUNCER DEMO COMPLETE: ALL CHECKS PASSED ==="
    exit 0
fi
echo "=== 01-RLS-PGBOUNCER DEMO COMPLETE: CHECKS FAILED ==="
exit 1
