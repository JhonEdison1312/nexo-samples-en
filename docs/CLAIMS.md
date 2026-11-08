# CV Claims Mapping

| CV Claim | Sample | File | Command |
|-----------|--------|------|----------|
| C++20 | 03-edge-pipeline | samples/03-edge-pipeline/src/include/hal/IBiometricSensor.h | `bash samples/03-edge-pipeline/harness/test_edge_pipeline.sh` |
| PHP 8 | 01-rls-pgbouncer | samples/01-rls-pgbouncer/src/auth_middleware.php | `php -l samples/01-rls-pgbouncer/src/auth_middleware.php` |
| PostgreSQL RLS | 01-rls-pgbouncer | samples/01-rls-pgbouncer/src/auth_middleware.php | `bash samples/01-rls-pgbouncer/harness/test_pgbouncer_leak.sh` |
| PgBouncer SET LOCAL | 01-rls-pgbouncer | samples/01-rls-pgbouncer/src/auth_middleware.php | `bash samples/01-rls-pgbouncer/harness/test_pgbouncer_leak.sh` |
| AES-256-GCM | 03-edge-pipeline | samples/03-edge-pipeline/src/encryption.cpp | `bash samples/03-edge-pipeline/harness/test_edge_pipeline.sh` |
| HMAC audit chain | 02-audit-chain | samples/02-audit-chain/src/worker_audit.php | `bash samples/02-audit-chain/harness/test_tampering.sh` |
| LLM integration | 04-nodus-parser | samples/04-nodus-parser/src/nexus_llm.php | `php samples/04-nodus-parser/harness/test_parser.php` |
| Redis reliable queue / DLQ | 05-redis-reliable-queue | samples/05-redis-reliable-queue/src/worker_biometric_queue.php | `python3 samples/05-redis-reliable-queue/harness/test_queue.py` |
| PostgreSQL table partitioning | 06-table-partitioning | samples/06-table-partitioning/src/create_monthly_partition.sh | `bash samples/06-table-partitioning/harness/test_partitioning.sh` |

## Tier 3 Audit — Claims Present in ORIGIN but Not Extracted

| Claim | Status | Evidence |
|-------|--------|----------|
| Risk engine (multi-layer scoring) | EVIDENCED IN REPO — NOT EXTRACTED | `backend/api/routes/risk.php`, `RiskEngineV3.php`; too large for isolated extract |
| JWT / RBAC middleware | EVIDENCED IN REPO — NOT EXTRACTED | `_auth_middleware.php` (beyond RLS extract); RBAC capabilities in `nexus_semantic.php` |
| Docker / containerization | EVIDENCED IN REPO — NOT EXTRACTED | `Dockerfile`, `docker-compose.yml` in ORIGIN root; prototype-level, no registry target |
| Kubernetes / multi-region | NOT IN REPO | No k8s manifests, Helm charts, or multi-region config found in ORIGIN |
| Database migrations framework | NOT IN REPO | Schema managed via `sql/schema.sql` and partition scripts; no migration runner |
