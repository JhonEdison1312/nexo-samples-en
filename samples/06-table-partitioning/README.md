# Monthly Table Partitioning

## Purpose

Demonstrates declarative PostgreSQL RANGE partitioning management: automated
monthly partition creation across 8 parent tables, idempotent CREATE TABLE IF
NOT EXISTS guards, and a retention-based drop invoker that calls a stored
procedure to prune expired partitions.

## Where it fits

NEXO accumulates append-only time-series rows in 8 tables (attendance events,
audit logs, messages, alerts, commands). Partition-by-month enables pruning
without locking live rows and keeps index sizes bounded.

## Origin

- `create_monthly_partition.sh`: `backend/api/infra/scripts/create_monthly_partition.sh` (lines 1-57)
- `drop_old_partitions.sh`: `backend/api/infra/scripts/drop_old_partitions.sh` (lines 1-24)
- Transformations: 0 substitutions applied (clean code extracts).

## What to look at

- `create_monthly_partition.sh` (lines 24-34): Associative array mapping 8
  partitioned parent tables to their range column — single-source-of-truth for
  the full partition topology.

- `create_monthly_partition.sh` (lines 43-56): Loop with EXISTS guard — skips
  already-created partitions; any failure sets a non-zero exit so cron alerts.

- `create_monthly_partition.sh` (line 36): Optional `[YYYY-MM]` and `[table]`
  arguments for ad-hoc backfill of a specific month or single table.

- `drop_old_partitions.sh` (line 22): Delegates to `fn_drop_old_partitions(N)`
  (a PL/pgSQL stored procedure) — the shell script is just a cron shim with
  logging; drop logic lives in the database where it can be transactional.

## Run it

```bash
# Requires PostgreSQL at localhost:15432 (tools/env/up.sh)

bash samples/06-table-partitioning/harness/test_partitioning.sh

```

Expected output is in `EXPECTED_OUTPUT.txt`.  
If PostgreSQL is offline, shellcheck (S1) still runs in isolation.

## Design decisions and trade-offs

- **DDL requires `ADMIN_DATABASE_URL`**: Partition CREATE requires a role with
  DDL privilege. Separating it from `DATABASE_URL` (application read/write role)
  prevents the API process from ever issuing DDL in normal operation.

- **Shell over migration framework**: No ORM or migration runner can reliably
  pre-create next month's partition via a cron. A shell script calling `psql`
  is the right tool: transparent, auditable, and runnable from crontab without
  a language runtime.

- **Stored procedure for drops**: `fn_drop_old_partitions` runs in one
  transaction and can inspect pg_class safely. Doing this in shell would
  require assembling a dynamic DROP list from shell string manipulation —
  error-prone and not transactional.

## Limitations and what I would change

- The partition granularity is fixed at monthly. For very high-throughput tables
  a weekly or daily granularity would reduce individual partition size.

- Partition creation is currently a manual or cron trigger; an event-driven
  approach (trigger creation 7 days before month end) would be more robust.
