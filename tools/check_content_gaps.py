#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Check each sample's CV claim mapping and identify content gaps.
"""
import json
import sys
from pathlib import Path

# CV claims from user's CV
cv_claims = {
    "Multi-tenant SQL: PostgreSQL Row-Level Security under PgBouncer transaction pooling": "01-rls-pgbouncer",
    "Security by design: HMAC audit chain": "02-audit-chain",
    "Edge node (C++20): offline-first, SQLite, HAL, simulators, E2E validation": "03-edge-pipeline",
    "Nodus (AI assistant): LLM parser and composer": "04-nodus-parser"
}

print("=== SAMPLE -> CV CLAIM MAPPING ===\n")

for sample_dir in sorted(Path('samples').iterdir()):
    if not sample_dir.is_dir():
        continue
    sample_id = sample_dir.name
    print(f"Sample: {sample_id}")
    print(f"  Files in src: {list((sample_dir / 'src').glob('*')) if (sample_dir / 'src').exists() else 'None'}")
    print(f"  Files in harness: {list((sample_dir / 'harness').glob('*')) if (sample_dir / 'harness').exists() else 'None'}")

    # Check README
    readme = sample_dir / 'README.md'
    if readme.exists():
        content = readme.read_text()
        print(f"  README sections: {[line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')][:5]}")
    print()

print("\n=== CHECKING FOR MISSING SQL IN ORIGIN ===\n")

# Check for RLS policy SQL
origin_arg = sys.argv[1] if len(sys.argv) > 1 else str(Path.cwd().parent)
rls_files = list(Path(origin_arg).rglob('*.sql'))
print(f"Total SQL files in ORIGIN: {len(rls_files)}")

# Search for RLS policy keywords
rls_found = []
for sql_file in rls_files:
    content = sql_file.read_text()
    if 'ROW LEVEL SECURITY' in content or 'row level security' in content.lower():
        rls_found.append(sql_file)

print(f"SQL files mentioning RLS: {len(rls_found)}")
for f in rls_found[:5]:
    print(f"  {f}")

# Search for audit trigger
audit_found = []
for sql_file in rls_files:
    content = sql_file.read_text()
    if 'chain_hash' in content or 'global_audit_logs' in content:
        audit_found.append(sql_file)

print(f"\nSQL files mentioning audit chain: {len(audit_found)}")
for f in audit_found[:5]:
    print(f"  {f}")
