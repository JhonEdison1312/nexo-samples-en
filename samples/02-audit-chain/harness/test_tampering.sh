#!/usr/bin/env bash
# ADDED FOR THIS SAMPLE
# Test audit chain integrity verification and tampering detection:
# 1. Valid chain -> status: ok
# 2. Tamper middle record -> status: compromised
# 3. Delete record -> status: compromised
# 4. Reorder records -> status: compromised
# Every check is a real assertion; the banner prints only if all pass.
set -uo pipefail

PG_HOST="${NEXO_PG_HOST:-127.0.0.1}"
PG_PORT="${NEXO_PG_PORT:-15432}"
DB_NAME="${NEXO_DB_NAME:-nexo}"
DB_USER="${NEXO_DB_USER:-nexo_app}"
export PGPASSWORD="${NEXO_DB_PASSWORD:-nexo_secret}"
SOCKET_DIR="${NEXO_SOCKET_DIR:-/tmp/nexo_env/sockets}"
FAIL=0

if [[ -d "${SOCKET_DIR}" ]]; then
    PSQL_CMD=(psql -h "${SOCKET_DIR}" -p "${PG_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -A -t -q)
else
    PSQL_CMD=(psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -A -t -q)
fi

json_status() {
    printf '%s' "$1" | grep -o '"status"[^,}]*' | head -n1 | sed 's/.*"status"[[:space:]]*:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}.*/\1/'
}

check() {
    local name="$1" actual="$2" expected="$3"
    if [[ "${actual}" == "${expected}" ]]; then
        echo "  [PASS] ${name}: status=${actual}"
    else
        echo "  [FAIL] ${name}: expected status=${expected}, got '${actual}'"
        FAIL=1
    fi
}

echo "=== 02-AUDIT-CHAIN VERIFICATION DEMO ==="
echo "Target: ${DB_NAME} as ${DB_USER}"

"${PSQL_CMD[@]}" -c "SELECT set_config('app.nexo_hmac_secret', 'nexo-audit-hmac-sha256-secret-key-32b', false);" >/dev/null

SEED_SQL='SELECT set_config('"'"'app.nexo_hmac_secret'"'"', '"'"'nexo-audit-hmac-sha256-secret-key-32b'"'"', false);
TRUNCATE TABLE global_audit_logs;
INSERT INTO global_audit_logs (school_id, performed_by_user_id, action_type, action_details, ip_address, created_at)
VALUES
  ('"'"'11111111-1111-1111-1111-111111111111'"'"', '"'"'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"'"', '"'"'AUTH_LOGIN'"'"', '"'"'{"method": "password"}'"'"', '"'"'10.0.0.1'"'"', NOW() + INTERVAL '"'"'1 second'"'"'),
  ('"'"'11111111-1111-1111-1111-111111111111'"'"', '"'"'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"'"', '"'"'STUDENT_VIEW'"'"', '"'"'{"student_id": 101}'"'"', '"'"'10.0.0.1'"'"', NOW() + INTERVAL '"'"'2 seconds'"'"'),
  ('"'"'11111111-1111-1111-1111-111111111111'"'"', '"'"'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"'"', '"'"'ATTENDANCE_OVERRIDE'"'"', '"'"'{"record_id": 55}'"'"', '"'"'10.0.0.1'"'"', NOW() + INTERVAL '"'"'3 seconds'"'"'),
  ('"'"'11111111-1111-1111-1111-111111111111'"'"', '"'"'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"'"', '"'"'REPORT_GENERATE'"'"', '"'"'{"report": "monthly"}'"'"', '"'"'10.0.0.1'"'"', NOW() + INTERVAL '"'"'4 seconds'"'"'),
  ('"'"'11111111-1111-1111-1111-111111111111'"'"', '"'"'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"'"', '"'"'AUTH_LOGOUT'"'"', '"'"'{"duration": 1800}'"'"', '"'"'10.0.0.1'"'"', NOW() + INTERVAL '"'"'5 seconds'"'"');'

validate() {
    "${PSQL_CMD[@]}" <<'SQL' | tail -n1
SELECT set_config('app.nexo_hmac_secret', 'nexo-audit-hmac-sha256-secret-key-32b', false);
SELECT fn_validate_audit_chain();
SQL
}

echo ""
echo "--- TEST 1: Valid Sequential Chain Generation ---"
echo "${SEED_SQL}" | "${PSQL_CMD[@]}" >/dev/null
echo "Inserted 5 sequential audit events."
RES_1_JSON=$(validate)
echo "Validation Result: ${RES_1_JSON}"
check "TEST 1 valid chain" "$(json_status "${RES_1_JSON}")" "ok"

echo ""
echo "--- TEST 2: Detect Middle Record Tampering ---"
"${PSQL_CMD[@]}" <<'SQL' >/dev/null
SELECT set_config('app.nexo_hmac_secret', 'nexo-audit-hmac-sha256-secret-key-32b', false);
ALTER TABLE global_audit_logs DISABLE TRIGGER trg_audit_chain;
UPDATE global_audit_logs SET action_details = '{"record_id": 55, "tampered": true}' WHERE action_type = 'ATTENDANCE_OVERRIDE';
ALTER TABLE global_audit_logs ENABLE TRIGGER trg_audit_chain;
SQL
echo "Modified payload of middle event ('ATTENDANCE_OVERRIDE') directly in database."
RES_2_JSON=$(validate)
echo "Validation Result: ${RES_2_JSON}"
check "TEST 2 middle tamper" "$(json_status "${RES_2_JSON}")" "compromised"

echo ""
echo "--- TEST 3: Detect Record Deletion ---"
echo "${SEED_SQL}" | "${PSQL_CMD[@]}" >/dev/null
"${PSQL_CMD[@]}" <<'SQL' >/dev/null
SELECT set_config('app.nexo_hmac_secret', 'nexo-audit-hmac-sha256-secret-key-32b', false);
ALTER TABLE global_audit_logs DISABLE TRIGGER trg_audit_chain;
DELETE FROM global_audit_logs WHERE action_type = 'ATTENDANCE_OVERRIDE';
ALTER TABLE global_audit_logs ENABLE TRIGGER trg_audit_chain;
SQL
echo "Deleted event #3 ('ATTENDANCE_OVERRIDE') from sequence."
RES_3_JSON=$(validate)
echo "Validation Result: ${RES_3_JSON}"
check "TEST 3 deletion" "$(json_status "${RES_3_JSON}")" "compromised"

echo ""
echo "--- TEST 4: Detect Record Reordering ---"
"${PSQL_CMD[@]}" <<'SQL' >/dev/null
SELECT set_config('app.nexo_hmac_secret', 'nexo-audit-hmac-sha256-secret-key-32b', false);
TRUNCATE TABLE global_audit_logs;
INSERT INTO global_audit_logs (school_id, performed_by_user_id, action_type, action_details, ip_address, created_at)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'AUTH_LOGIN', '{"method": "password"}', '10.0.0.1', NOW() + INTERVAL '1 second'),
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'STUDENT_VIEW', '{"student_id": 101}', '10.0.0.1', NOW() + INTERVAL '2 seconds'),
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'ATTENDANCE_OVERRIDE', '{"record_id": 55}', '10.0.0.1', NOW() + INTERVAL '3 seconds'),
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'REPORT_GENERATE', '{"report": "monthly"}', '10.0.0.1', NOW() + INTERVAL '4 seconds'),
  ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'AUTH_LOGOUT', '{"duration": 1800}', '10.0.0.1', NOW() + INTERVAL '5 seconds');
ALTER TABLE global_audit_logs DISABLE TRIGGER trg_audit_chain;
UPDATE global_audit_logs SET created_at = NOW() + INTERVAL '10 seconds' WHERE action_type = 'AUTH_LOGIN';
ALTER TABLE global_audit_logs ENABLE TRIGGER trg_audit_chain;
SQL
echo "Moved event #1 ('AUTH_LOGIN') timestamp past event #5, disrupting chain sequence."
RES_4_JSON=$(validate)
echo "Validation Result: ${RES_4_JSON}"
check "TEST 4 reorder" "$(json_status "${RES_4_JSON}")" "compromised"

echo ""
if [[ "${FAIL}" -eq 0 ]]; then
    echo "=== 02-AUDIT-CHAIN DEMO COMPLETE: ALL CHECKS PASSED ==="
    exit 0
fi
echo "=== 02-AUDIT-CHAIN DEMO COMPLETE: CHECKS FAILED ==="
exit 1
