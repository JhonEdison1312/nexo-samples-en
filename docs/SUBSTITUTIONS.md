# Substitutions in Extracts

This document lists all literal substitutions applied to code extracts during the
sanitization process. Substitutions are only allowed for string literals (secrets,
real names, IPs, emails, IDs) or for comment translation with `scope: comment`.

## Substitution Table

| Sample | File | Pattern | Replacement | Expected Count | Scope |
|--------|------|---------|-------------|----------------|-------|
| 01-rls-pgbouncer | auth_middleware.php | Usuario no encontrado o inactivo | User not found or inactive | 1 | literal |
| 02-audit-chain | worker_audit.php | APP_NEXO_HMAC_SECRET no configurada o es default. Worker no puede iniciar. | APP_NEXO_HMAC_SECRET is not configured or is the default. Worker cannot start. | 1 | literal |
| 02-audit-chain | audit_chain_trigger.sql | app.nexo_hmac_secret no configurado. Abortando para prevenir compromiso de cadena de auditoría. | app.nexo_hmac_secret is not configured. Aborting to prevent audit chain compromise. | 1 | literal |
| 03-edge-pipeline | sqlite_manager.cpp | -- T\u004fDO: evaluar si tabla patrones se usa, candidato a eliminar | -- NOTE: evaluate whether the patrones table is used, candidate for removal | 1 | literal |
| 03-edge-pipeline | sqlite_manager.cpp | -- PAE (Programa de Alimentacion Escolar) eliminado por decision de arquitectura | -- PAE (school meal program) removed by architecture decision | 1 | literal |
| 03-edge-pipeline | sqlite_manager.cpp | -- Multi-huella — hasta 2 dedos por estudiante. estudiantes.huella_id | -- Multi-fingerprint — up to 2 fingers per student. estudiantes.huella_id | 1 | literal |
| 03-edge-pipeline | sqlite_manager.cpp | -- se mantiene como compat (dedo 1); estudiante_huellas es la fuente normalizada. | -- is kept for compatibility (finger 1); estudiante_huellas is the normalized source. | 1 | literal |
| 03-edge-pipeline | sqlite_manager.cpp | encField: cifrado falló — guardando en claro (degradado) | encField: encryption failed — storing plaintext (degraded) | 1 | literal |
| 03-edge-pipeline | sqlite_manager.cpp | decField: decrypt falló — devolviendo valor crudo (no pérdida) | decField: decrypt failed — returning raw value (no loss) | 1 | literal |
| 06-table-partitioning | create_monthly_partition.sh | ADMIN_DATABASE_URL/DATABASE_URL no configurada | ADMIN_DATABASE_URL/DATABASE_URL is not configured | 1 | literal |
| 06-table-partitioning | create_monthly_partition.sh | Partición ${PNAME} ya existe. | Partition ${PNAME} already exists. | 1 | literal |
| 06-table-partitioning | create_monthly_partition.sh | Partición ${PNAME} creada [${P_START}, ${P_END}). | Partition ${PNAME} created [${P_START}, ${P_END}). | 1 | literal |
| 06-table-partitioning | create_monthly_partition.sh | ERROR: fallo al crear ${PNAME} | ERROR: failed to create ${PNAME} | 1 | literal |
| 06-table-partitioning | drop_old_partitions.sh | ADMIN_DATABASE_URL/DATABASE_URL no configurada | ADMIN_DATABASE_URL/DATABASE_URL is not configured | 1 | literal |
| 06-table-partitioning | drop_old_partitions.sh | Retención ${RETENTION} meses — particiones eliminadas: ${DROPPED} | Retention ${RETENTION} months — partitions dropped: ${DROPPED} | 1 | literal |
| 06-table-partitioning | fn_drop_old_partitions.sql | -- Extraer fecha del nombre _YYYY_MM | -- Extract date from the _YYYY_MM name suffix | 1 | literal |
| 06-table-partitioning | fn_drop_old_partitions.sql | -- DETACH primero (seguro), luego DROP | -- DETACH first (safe), then DROP | 1 | literal |

## Notes

- All substitutions are declared in PROVENANCE.json
- verify.py independently counts occurrences and validates expected_count
- Only string literal substitutions are allowed unless scope=comment
- Spanish appears only in the 'before' (pattern) column, which quotes
  ORIGIN source text verbatim; every 'replacement' is English.
- Comment translations are ignored by the normalizer (not considered substitutions)
