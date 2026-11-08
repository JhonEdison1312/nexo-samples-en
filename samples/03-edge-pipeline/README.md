# Edge Pipeline

## Purpose

Demonstrates an offline-first C++20 edge node with hardware abstraction layer (HAL), SQLite local outbox, AES-256-GCM encryption, cloud synchronization with retry accounting, and anti-replay defense.

## Where it fits

NEXO's edge devices in educational centers that record biometric attendance events offline and sync them securely to the central API when network connectivity is restored.

## Origin

- Path: `backend/edge/include/hal/IBiometricSensor.h` (lines 1-56)
- Path: `backend/edge/src/hardware/dev_stub/DevStubBiometricSensor.cpp` (lines 1-54)
- Path: `backend/edge/src/base_de_datos/sqlite_manager.cpp` (lines 1-723)
- Path: `backend/edge/src/base_de_datos/encryption.cpp` (lines 1-498)
- Path: `backend/edge/src/base_de_datos/cloud_manager.cpp` (lines 1-168)
- Transformations: 0 substitutions applied (clean code extract matching mother repo commit).

## What to look at

- `encryption.cpp` (lines 106-136): Fail-closed hardware key enforcement; dev fallback requires `NEXO_ALLOW_DEV_KEY_FALLBACK=1` (mode 0600).
- `encryption.cpp` (lines 188-267): AES-256-GCM encryption with 12-byte random IV and 16-byte authentication tag.
- `sqlite_manager.cpp` (lines 37-95): Outbox table setup with `PRAGMA journal_mode=WAL` and `synchronous=EXTRA`.
- `cloud_manager.cpp` (lines 52-168): Encrypted payload assembly and sync retry tracking.
- `IBiometricSensor.h` (lines 28-55): Hardware abstraction contract separating business logic from biometric sensors.

## Run it

Native user-space:

```bash
./samples/03-edge-pipeline/harness/test_edge_pipeline.sh

```

Docker Compose:

```bash
cd samples/03-edge-pipeline/harness && docker compose up --build

```

## Design decisions and trade-offs

- **Fail-Closed Hardware Binding**: If hardware-bound key acquisition fails, the node refuses to persist keys in plaintext unless `NEXO_ALLOW_DEV_KEY_FALLBACK=1` is explicitly set for development simulators. SIMULATED: The harness demo (`main_demo.cpp`) simulates a mock cloud server; it does not make real network calls or use real hardware keys.
- **SQLite Outbox Pattern**: Biometric events persist immediately to local SQLite before any network call, preventing data loss across power cuts or network drops.
- **Server Deduplication & Replay Protection**: Payloads include unique nonces verified via Redis `SET key 1 NX EX 604800` to prevent replay attacks.

## Limitations and what I would change

- **Fail-open Nonce Verification**: The private ingest handler `backend/api/api.php` (private file, not part of this repository) lines 363-380 permit requests when Redis is down, prioritizing attendance capture over strict replay protection. In high-assurance environments, this should fail closed or fall back to an indexed PostgreSQL table.
- **Key Recovery**: Hardware-bound keys cannot be extracted; device replacement requires cloud re-enrollment. Adding TPM-backed attestation would streamline fleet provisioning.
- **Legacy Plaintext Key Fallback**: `encryption.cpp:139-158` contains a fallback to load plaintext keys from a 32-byte file for legacy/non-RPi environments. This is used when hardware-bound encrypted keys cannot be decrypted (e.g., SD card moved to different hardware). In a strict fail-closed deployment, this fallback should be removed. SIMULATED: The harness demo server is SIMULATED; it does not use real hardware or encrypted keys.
- **Field-Level Encryption Degraded Mode**: `sqlite_manager.cpp` `encField`/`decField` (lines ~171-195) store and return PLAINTEXT when no encryption key is provisioned or encryption fails, and `decField` accepts legacy plaintext values without the `enc:v1:` prefix. PII at rest is therefore only protected while a key is provisioned; a strict deployment should fail closed here too.

## Related samples

- `01-rls-pgbouncer`: Multi-tenant session isolation in the ingestion API.
- `02-audit-chain`: Tamper-evident HMAC audit trail for recorded events.
