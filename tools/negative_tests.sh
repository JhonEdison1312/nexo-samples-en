#!/usr/bin/env bash
# ADDED FOR THIS SAMPLE
# Negative controls: prove each test actually fails when the thing it
# verifies is broken. Every sabotage MUST produce a non-zero test exit;
# the environment is restored after each case. Exits non-zero if any
# sabotage goes undetected.
#
# Usage: tools/env/up.sh first (or this script starts it), then:
#   bash tools/negative_tests.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit

PSQL_ADMIN=(psql -h /tmp -p 15432 -U nexo_admin -d nexo -v ON_ERROR_STOP=1 -q)
PASS=0; FAIL=0

restore_env() {
    tools/env/up.sh >/dev/null 2>&1
}

expect_fail() { # expect_fail <name> <command...>
    local name="$1"; shift
    echo ""
    echo "=== NEGATIVE: $name ==="
    "$@" > /tmp/neg_last.log 2>&1
    local rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "[PASS] test exited non-zero ($rc) as required"
        tail -n 8 /tmp/neg_last.log | sed 's/^/    /'
        PASS=$((PASS+1))
    else
        echo "[FAIL] test PASSED despite sabotage — assertion is not real"
        FAIL=$((FAIL+1))
    fi
}

# Ensure env is up
if ! pg_isready -h /tmp -p 15432 >/dev/null 2>&1; then
    tools/env/up.sh >/dev/null
fi

echo "=== NEGATIVE TESTS: each sabotage must be caught ==="

# --- 1. RLS disabled -> test-01 must fail (no-context rows become visible)
echo ""
echo "--- sabotage: DISABLE ROW LEVEL SECURITY on students ---"
"${PSQL_ADMIN[@]}" -c "ALTER TABLE students DISABLE ROW LEVEL SECURITY;"
expect_fail "RLS disabled (test-01)" make test-01
"${PSQL_ADMIN[@]}" -c "ALTER TABLE students ENABLE ROW LEVEL SECURITY;"

# --- 2. Audit chain function dropped -> test-02 must fail
echo ""
echo "--- sabotage: DROP FUNCTION fn_validate_audit_chain ---"
"${PSQL_ADMIN[@]}" -c "DROP FUNCTION IF EXISTS fn_validate_audit_chain(uuid);"
expect_fail "audit chain fn dropped (test-02)" make test-02
restore_env  # reloads src/audit_chain_trigger.sql

# --- 3. Redis down -> test-03 must fail with 'Redis is down', test-05 must fail
echo ""
echo "--- sabotage: Redis stopped ---"
redis-cli -p 16379 shutdown nosave >/dev/null 2>&1 || true
sleep 1
expect_fail "Redis down (test-03)" make test-03
if grep -qi "redis is down" /tmp/neg_last.log; then
    echo "[PASS] failure message mentions Redis being down"
    PASS=$((PASS+1))
else
    echo "[FAIL] failure did not clearly report Redis being down"
    FAIL=$((FAIL+1))
fi
expect_fail "Redis down (test-05)" python3 samples/05-redis-reliable-queue/harness/test_queue.py
restore_env

# --- 4. Partition retention fn dropped -> test-06 must fail
echo ""
echo "--- sabotage: DROP FUNCTION fn_drop_old_partitions ---"
"${PSQL_ADMIN[@]}" -c "DROP FUNCTION IF EXISTS fn_drop_old_partitions(integer);"
expect_fail "partition fn dropped (test-06)" make test-06
restore_env

# --- sanity: env restored, all tests pass again
echo ""
echo "=== RESTORE CHECK: tests must pass again ==="
for t in test-01 test-02 test-03 test-05 test-06; do
    if make "$t" >/dev/null 2>&1; then
        echo "[PASS] $t passes after restore"
        PASS=$((PASS+1))
    else
        echo "[FAIL] $t still failing after restore"
        FAIL=$((FAIL+1))
    fi
done

echo ""
echo "=== NEGATIVE TESTS SUMMARY ==="
echo "checks passed: $PASS"
echo "checks failed: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    echo "NEGATIVE TESTS: FAIL"
    exit 1
fi
echo "NEGATIVE TESTS: ALL SABOTAGES DETECTED"
exit 0
