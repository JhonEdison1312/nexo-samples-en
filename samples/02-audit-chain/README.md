# HMAC Audit Chain

## Purpose

Demonstrates tamper-evident audit logging using cryptographic HMAC-SHA256 hash chaining to detect modifications, deletions, or sequence disruptions.

## Where it fits

Audit pipeline where state mutations emit append-only records to `global_audit_logs`. A database trigger computes a forward cryptographic chain per tenant using a server-side HMAC secret.

## Origin

- Path: `backend/api/workers/worker_audit.php` (lines 70-189)
- Path: `sql/schema.sql` (lines 1362-1456)
- Transformations: 0 substitutions applied (clean code extract matching mother repo commit)

## What to look at

- `src/audit_chain_trigger.sql`: `fn_calculate_audit_hash` derives an HMAC-SHA256 signature binding the previous record's hash, actor ID, action payload, and timestamp.
- `src/audit_chain_trigger.sql`: `fn_audit_chain_trigger` automatically queries `prev_audit_id` and binds `chain_hash` before insertion.
- `src/audit_chain_trigger.sql`: `fn_validate_audit_chain` iteratively traverses records in chronological order and reports the exact broken record ID upon discrepancy.

## Run it

Native user-space execution:

```bash
tools/env/up.sh
./samples/02-audit-chain/harness/test_tampering.sh

```

Docker route (the native route above is the primary one):

```bash
cd samples/02-audit-chain/harness && docker compose up -d --wait && NEXO_PG_PORT=15433 NEXO_SOCKET_DIR= ./test_tampering.sh

```

## Design decisions and trade-offs

- **HMAC over plain hash**: Requires `app.nexo_hmac_secret`. A database attacker without access to application server configuration cannot recalculate valid signatures after tampering.
- **Per-tenant chaining**: Scoping chains by `school_id` avoids row locks on global serialization, allowing parallel ingestion across institutions.

## Limitations and what I would change

- The trigger executes `SELECT ... FOR UPDATE` on the latest tenant record, creating a serialized bottleneck under intense write concurrency within a single tenant.
- In high-load deployed environments, I would offload chain calculation to an async queue worker with batching.

## Related samples

- `01-rls-pgbouncer`: Multi-tenant isolation using SET LOCAL
- `03-edge-pipeline`: Offline biometric event logging and sync
