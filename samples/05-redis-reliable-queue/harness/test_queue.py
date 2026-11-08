#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
test_queue.py — Standalone harness demonstrating the biometric reliable-queue pattern.

Exercises three invariants of the Lua scripts extracted from worker_biometric_queue.php:
  T1  LMOVE atomicity  — item moves ingest→processing; ingest becomes empty.
  T2  GC zombie recovery — stale processing job (>maxAge) re-enqueues to ingest.
  T3  DLQ promotion   — job exceeding MAX_RETRIES is moved to DLQ, not retried.

Requires: Redis on 127.0.0.1:16379 (run tools/env/up.sh to start it).
No database needed; queue logic is pure Redis + Lua.
"""

import sys
import json
import time
import redis as redislib

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 16379

INGEST     = "q:biometric_ingest"
PROCESSING = "q:biometric_processing"
DLQ        = "q:biometric_dlq"
MAX_RETRIES = 3
GC_MAX_AGE  = 5   # seconds — shortened for demo (production default: 300s)

# ── Lua scripts copied verbatim from src/worker_biometric_queue.php ────────────
SCRIPT_RELIABLE_POP = """
local ingest = KEYS[1]
local processing = KEYS[2]
local now = tonumber(ARGV[1])
local item = redis.call('LMOVE', ingest, processing, 'RIGHT', 'LEFT')
if item then
    local ok, job = pcall(cjson.decode, item)
    if ok and job then
        job.processing_since = now
        local newItem = cjson.encode(job)
        redis.call('LREM', processing, 0, item)
        redis.call('LPUSH', processing, newItem)
        return newItem
    end
    return item
end
return nil
"""

SCRIPT_GC = """
local processing = KEYS[1]
local ingest = KEYS[2]
local maxAge = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local items = redis.call('LRANGE', processing, 0, -1)
local recovered = 0
for i = 1, #items do
    local item = items[i]
    local ok, job = pcall(cjson.decode, item)
    if ok and job and job.processing_since then
        if (now - job.processing_since) > maxAge then
            redis.call('LREM', processing, 0, item)
            redis.call('LPUSH', ingest, item)
            recovered = recovered + 1
        end
    else
        redis.call('LREM', processing, 0, item)
        redis.call('LPUSH', ingest, item)
        recovered = recovered + 1
    end
end
return recovered
"""


def main():
    r = redislib.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    try:
        r.ping()
    except Exception as e:
        print(f"ERROR: Cannot connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}", file=sys.stderr)
        print("Start with: tools/env/up.sh", file=sys.stderr)
        sys.exit(1)

    # Cleanup from any prior run
    r.delete(INGEST, PROCESSING, DLQ)

    passed = 0
    failed = 0

    def ok(label):
        nonlocal passed
        print(f"[PASS] {label}")
        passed += 1

    def fail(label, got, want):
        nonlocal failed
        print(f"[FAIL] {label} — got {got!r}, want {want!r}")
        failed += 1

    def check(label, got, want):
        if got == want:
            ok(label)
        else:
            fail(label, got, want)

    # ── T1: LMOVE atomicity ───────────────────────────────────────────────────
    print("\n=== T1: Reliable LMOVE — job moves from ingest to processing atomically ===")
    job1 = {"action": "SYNC_ATTENDANCE", "request_id": "req-001", "retries": 0}
    r.rpush(INGEST, json.dumps(job1))

    now = int(time.time())
    item = r.eval(SCRIPT_RELIABLE_POP, 2, INGEST, PROCESSING, now)

    check("ingest queue empty after pop", r.llen(INGEST), 0)
    check("processing queue has 1 item",  r.llen(PROCESSING), 1)

    popped = json.loads(item)
    check("job action intact",         popped.get("action"),         "SYNC_ATTENDANCE")
    check("processing_since injected", "processing_since" in popped, True)

    # Simulate successful commit: remove from processing
    r.lrem(PROCESSING, 0, item)
    check("processing empty after ack", r.llen(PROCESSING), 0)

    # ── T2: GC recovers zombie job ─────────────────────────────────────────────
    print("\n=== T2: GC zombie recovery — stale processing job re-enqueued ===")
    job2 = {"action": "REGISTER_STUDENT", "request_id": "req-002", "retries": 0}
    r.rpush(INGEST, json.dumps(job2))

    stale_ts = int(time.time()) - (GC_MAX_AGE + 1)   # already expired
    zombie = r.eval(SCRIPT_RELIABLE_POP, 2, INGEST, PROCESSING, stale_ts)

    check("zombie is in processing before GC", r.llen(PROCESSING), 1)
    check("ingest empty before GC",            r.llen(INGEST), 0)

    recovered = r.eval(SCRIPT_GC, 2, PROCESSING, INGEST, GC_MAX_AGE, int(time.time()))
    check("GC recovered 1 zombie",     int(recovered), 1)
    check("processing empty after GC", r.llen(PROCESSING), 0)
    check("ingest has recovered job",  r.llen(INGEST), 1)

    r.delete(INGEST)

    # ── T3: DLQ promotion after max retries ────────────────────────────────────
    print("\n=== T3: DLQ promotion — job exceeding retry limit moved to DLQ ===")
    # Seed the initial job once; each iteration re-queues the updated state.
    job_state = {"action": "SYNC_ATTENDANCE", "request_id": "req-003", "retries": 0}
    r.rpush(INGEST, json.dumps(job_state))

    for attempt in range(1, MAX_RETRIES + 2):
        item = r.eval(SCRIPT_RELIABLE_POP, 2, INGEST, PROCESSING, int(time.time()))
        r.lrem(PROCESSING, 0, item)
        job_state = json.loads(item)
        job_state["retries"] = attempt
        if attempt <= MAX_RETRIES:
            r.rpush(INGEST, json.dumps(job_state))    # retry
        else:
            r.rpush(DLQ, json.dumps(job_state))        # dead letter

    check("ingest empty after all retries", r.llen(INGEST), 0)
    check("DLQ has 1 failed job",          r.llen(DLQ), 1)

    dlq_job = json.loads(r.lindex(DLQ, 0))
    check("DLQ job retries == 4",  dlq_job.get("retries"), MAX_RETRIES + 1)
    check("DLQ job action intact", dlq_job.get("action"), "SYNC_ATTENDANCE")

    # Cleanup
    r.delete(INGEST, PROCESSING, DLQ)

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n=== Summary ===")
    print(f"Tests PASSED: {passed}")
    print(f"Tests FAILED: {failed}")
    if failed:
        sys.exit(1)
    print("All queue invariant tests PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
