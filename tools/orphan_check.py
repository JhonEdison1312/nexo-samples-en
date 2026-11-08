#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Orphan check: verify all files in samples/*/src are in PROVENANCE.json and vice versa.
"""
import json
from pathlib import Path

def orphan_check():
    with open('PROVENANCE.json') as f:
        provenance = json.load(f)

    # Get all files in samples/*/src
    src_files = set()
    for sample_dir in Path('samples').iterdir():
        if sample_dir.is_dir():
            src_path = sample_dir / 'src'
            if src_path.exists():
                for f in src_path.rglob('*'):
                    if f.is_file():
                        src_files.add(f"{sample_dir.name}/src/{f.relative_to(src_path)}")

    # Get all files in PROVENANCE.json
    provenance_files = set()
    for sample_id, sample_data in provenance.get('samples', {}).items():
        for extract in sample_data.get('extracts', []):
            provenance_files.add(f"{sample_id}/src/{extract['output_file']}")

    # Check for orphans
    src_only = src_files - provenance_files
    provenance_only = provenance_files - src_files

    print("=== ORPHAN CHECK ===")
    print(f"Files in samples/*/src: {len(src_files)}")
    print(f"Files in PROVENANCE.json: {len(provenance_files)}")

    if src_only:
        print(f"\nFiles in src but NOT in PROVENANCE.json ({len(src_only)}):")
        for f in sorted(src_only):
            print(f"  {f}")
    else:
        print("\nNo orphan files in src")

    if provenance_only:
        print(f"\nFiles in PROVENANCE.json but NOT in src ({len(provenance_only)}):")
        for f in sorted(provenance_only):
            print(f"  {f}")
    else:
        print("No orphan files in PROVENANCE.json")

    if not src_only and not provenance_only:
        print("\nORPHAN CHECK: PASS")
        return 0
    else:
        print("\nORPHAN CHECK: FAIL")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(orphan_check())
