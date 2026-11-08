# RLS + PgBouncer + SET LOCAL

## Purpose

Demonstrates PostgreSQL Row-Level Security (RLS) with PgBouncer transaction pooling using SET LOCAL to prevent cross-tenant context leaks across pooled connections.

## Where it fits

Multi-tenant core where PostgreSQL RLS policies enforce isolation by school_id. Transaction-scoped configuration parameters prevent state leakage when PgBouncer reuses physical connections.

## Origin

- Path: `backend/api/routes/_auth_middleware.php` (lines 665-725)
- Path: `sql/schema.sql` (lines 2282-2294)
- Transformations: 0 substitutions applied (clean code extract matching mother repo commit)

## What to look at

- `src/auth_middleware.php`: `beginTransaction()` followed by `set_config('app.current_school_id', ..., true)` ensures transaction-level scoping.
- `src/auth_middleware.php`: Authoritative context re-bind from database row after initial token parse.
- `src/rls_policies.sql`: RLS policies on `students` table utilizing `get_current_school_id()`.

## Run it

Native user-space execution:

```bash
tools/env/up.sh
./samples/01-rls-pgbouncer/harness/test_pgbouncer_leak.sh

```

Docker route (the native route above is the primary one):

```bash
cd samples/01-rls-pgbouncer/harness && docker compose up -d --wait && NEXO_PGBOUNCER_PORT=16431 ./test_pgbouncer_leak.sh

```

## Design decisions and trade-offs

- **Transaction scope over session**: In PgBouncer transaction pooling, session `SET` leaks to the next client sharing the backend connection. Passing `is_local=true` resets state on `COMMIT`.
- **Authoritative DB re-fetch**: Tokens are point-in-time snapshots. Role or tenant reassignments during active sessions are caught on the subsequent database lookup.

## Limitations and what I would change

- Requires every read query to execute inside an explicit transaction block, increasing roundtrips.
- In high-throughput architectures, I would evaluate tenant-prefixed schemas or dedicated connection pools per tier.

## Related samples

- `02-audit-chain`: Tamper-evident audit logging with HMAC chaining
- `03-edge-pipeline`: Offline attendance capture and synchronized ingestion
