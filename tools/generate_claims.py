#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Generate docs/CLAIMS.md by mapping CV claims to sample files and verification commands.
"""
from pathlib import Path

CLAIMS = {
    "C++20": {
        "sample": "03-edge-pipeline",
        "file": "samples/03-edge-pipeline/src/include/hal/IBiometricSensor.h",
        "command": "bash samples/03-edge-pipeline/harness/test_edge_pipeline.sh"
    },
    "PHP 8": {
        "sample": "01-rls-pgbouncer",
        "file": "samples/01-rls-pgbouncer/src/auth_middleware.php",
        "command": "php -l samples/01-rls-pgbouncer/src/auth_middleware.php"
    },
    "PostgreSQL RLS": {
        "sample": "01-rls-pgbouncer",
        "file": "samples/01-rls-pgbouncer/src/auth_middleware.php",
        "command": "bash samples/01-rls-pgbouncer/harness/test_pgbouncer_leak.sh"
    },
    "PgBouncer SET LOCAL": {
        "sample": "01-rls-pgbouncer",
        "file": "samples/01-rls-pgbouncer/src/auth_middleware.php",
        "command": "bash samples/01-rls-pgbouncer/harness/test_pgbouncer_leak.sh"
    },
    "AES-256-GCM": {
        "sample": "03-edge-pipeline",
        "file": "samples/03-edge-pipeline/src/encryption.cpp",
        "command": "bash samples/03-edge-pipeline/harness/test_edge_pipeline.sh"
    },
    "HMAC audit chain": {
        "sample": "02-audit-chain",
        "file": "samples/02-audit-chain/src/worker_audit.php",
        "command": "bash samples/02-audit-chain/harness/test_tampering.sh"
    },
    "LLM integration": {
        "sample": "04-nodus-parser",
        "file": "samples/04-nodus-parser/src/nexus_llm.php",
        "command": "php samples/04-nodus-parser/harness/test_parser.php"
    },
    "Redis reliable queue / DLQ": {
        "sample": "05-redis-reliable-queue",
        "file": "samples/05-redis-reliable-queue/src/worker_biometric_queue.php",
        "command": "python3 samples/05-redis-reliable-queue/harness/test_queue.py"
    },
    "PostgreSQL table partitioning": {
        "sample": "06-table-partitioning",
        "file": "samples/06-table-partitioning/src/create_monthly_partition.sh",
        "command": "bash samples/06-table-partitioning/harness/test_partitioning.sh"
    },
}

TIER3_AUDIT = [
    ("Risk engine (multi-layer scoring)",
     "EVIDENCED IN REPO — NOT EXTRACTED",
     "`backend/api/routes/risk.php`, `RiskEngineV3.php`; too large for isolated extract"),
    ("JWT / RBAC middleware",
     "EVIDENCED IN REPO — NOT EXTRACTED",
     "`_auth_middleware.php` (beyond RLS extract); RBAC capabilities in `nexus_semantic.php`"),
    ("Docker / containerization",
     "EVIDENCED IN REPO — NOT EXTRACTED",
     "`Dockerfile`, `docker-compose.yml` in ORIGIN root; prototype-level, no registry target"),
    ("Kubernetes / multi-region",
     "NOT IN REPO",
     "No k8s manifests, Helm charts, or multi-region config found in ORIGIN"),
    ("Database migrations framework",
     "NOT IN REPO",
     "Schema managed via `sql/schema.sql` and partition scripts; no migration runner"),
]


def generate_claims(check_only=False):
    out = "# CV Claims Mapping\n\n"
    out += "| CV Claim | Sample | File | Command |\n"
    out += "|-----------|--------|------|----------|\n"
    for claim, data in CLAIMS.items():
        out += f"| {claim} | {data['sample']} | {data['file']} | `{data['command']}` |\n"

    out += "\n## Tier 3 Audit — Claims Present in ORIGIN but Not Extracted\n\n"
    out += "| Claim | Status | Evidence |\n"
    out += "|-------|--------|----------|\n"
    for claim, status, evidence in TIER3_AUDIT:
        out += f"| {claim} | {status} | {evidence} |\n"

    if check_only:
        existing = Path("docs/CLAIMS.md")
        if not existing.exists() or existing.read_text(encoding="utf-8") != out:
            print("docs/CLAIMS.md is STALE — run tools/generate_claims.py")
            return 1
        print("docs/CLAIMS.md is up to date")
        return 0
    Path("docs/CLAIMS.md").write_text(out, encoding="utf-8")
    print("Generated docs/CLAIMS.md")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(generate_claims(check_only="--check" in sys.argv))
