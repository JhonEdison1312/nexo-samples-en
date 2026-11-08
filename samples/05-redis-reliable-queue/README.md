# Redis Reliable Queue with GC and DLQ

## Purpose

Demonstrates a zero-message-loss Redis queue pattern: atomic LMOVE into a
processing shadow list, zombie garbage collection via a Lua GC script, and
automatic promotion to a dead-letter queue after exhausting retry budget.

## Where it fits

NEXO's biometric event ingestion path. The edge devices enqueue attendance and
student-registration events at `queue:biometric_ingest`; this worker consumes
them with at-least-once delivery semantics even across worker crashes.

## Origin

- Path: `backend/api/workers/worker_biometric.php` (lines 720-939)
- Transformations: 0 substitutions applied (clean code extract matching mother repo commit)

## What to look at

- `worker_biometric_queue.php` (lines 1-25): `$scriptReliablePop` — Lua atomic
  LMOVE + `processing_since` timestamp injection. No application-level race.

- `worker_biometric_queue.php` (lines 27-47): `$scriptGc` — Lua GC that scans
  the processing list and re-enqueues any item older than `GC_MAX_AGE_SEC`.

- `worker_biometric_queue.php` (lines 69-115): Main loop — LMOVE pop, job
  dispatch, ack-after-commit pattern (`lRem` only on success).

- `worker_biometric_queue.php` (lines 159-174): DLQ promotion after 3 retries;
  circuit-breaker flag at `/tmp/redis_circuit_open`.

- `worker_biometric_queue.php` (lines 77-91): Outbox drain every 15 s — orphaned
  PROCESSING rows (worker died mid-flight) revert to PENDING.

## Run it

```bash
# Start Redis (if not already running)

tools/env/up.sh

# Run queue invariant tests (T1: atomicity, T2: GC recovery, T3: DLQ promotion)

python3 samples/05-redis-reliable-queue/harness/test_queue.py

```

Expected output is in `EXPECTED_OUTPUT.txt`.

## Design decisions and trade-offs

- **Two-list reliable queue**: LMOVE is atomic; the item is never invisible.
  If the worker crashes before ack, the GC recovers it after `GC_MAX_AGE_SEC`
  (default 300 s). This eliminates the lost-message window that a simple LPOP
  would have.

- **Lua scripts for atomicity**: Both LMOVE+timestamp injection and the GC
  scan-and-recover run inside a single Lua call. No multi-key MULTI/EXEC needed.

- **Outbox durable fallback**: Redis is the fast path. If Redis is unavailable,
  the edge API writes to `ingest_outbox` (PostgreSQL). The worker drains both
  every 15 s, so no message is lost even if Redis is down for minutes.

- **DLQ is a separate list**: `queue:biometric_dlq` is inspectable and
  replayable without touching the live queue.

## Limitations and what I would change

- The GC MAX_AGE (300 s) is a static config. A per-job TTL field would allow
  high-priority events to recover faster.

- `lRem` is O(N) on the processing list. For very high throughput a hash-based
  approach (job ID → claim expiry) would be O(1).
