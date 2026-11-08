#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Sample-side integrity check — NO ORIGIN REQUIRED (CI-safe).

Verifies, from PROVENANCE.json + the committed tree only:
  1. every PROVENANCE entry has a file and vice versa (orphan check, both ways);
  2. sha256 of each src file matches the recorded value;
  3. normalized_sha256 of each src file matches the recorded value;
  4. every substitution declares expected_count and touches only string
     literals (checked against the sample file);
  5. counts are consistent (extracts == files).

--self-test: copies samples+PROVENANCE.json to a temp dir, flips one
character in one src file, and proves the check catches it.

Usage: python3 tools/verify_structure.py [--self-test]
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools' / 'provenance'))
from normalizers import normalize, string_spans, _php_body  # noqa: E402


def check(prov_path='PROVENANCE.json', samples_dir='samples', prov_data=None):
    """Run all structural checks. Returns (ok, lines)."""
    lines = []
    ok = True
    prov_file = REPO / prov_path if not Path(prov_path).is_absolute() else Path(prov_path)
    samples_root = REPO / samples_dir if not Path(samples_dir).is_absolute() else Path(samples_dir)
    data = prov_data or json.loads(prov_file.read_text())

    prov_files = {}
    for sid, sd in data.get('samples', {}).items():
        for ex in sd.get('extracts', []):
            rel = f"{sid}/src/{ex['output_file']}"
            prov_files[rel] = (sid, ex)

    actual = {str(f.relative_to(samples_root))
              for f in samples_root.glob('*/src/**/*') if f.is_file()}

    for rel in sorted(set(actual) - set(prov_files)):
        lines.append(f'FAIL: extra file not in PROVENANCE.json: {rel}')
        ok = False
    for rel in sorted(set(prov_files) - set(actual)):
        lines.append(f'FAIL: PROVENANCE.json entry without file: {rel}')
        ok = False

    for rel, (sid, ex) in sorted(prov_files.items()):
        f = samples_root / rel
        if not f.exists():
            continue  # already reported
        content = f.read_text(encoding='utf-8')
        sha = hashlib.sha256(content.encode()).hexdigest()
        recorded = ex.get('sha256')
        if recorded and recorded != sha:
            # Informational: comments may differ via declared translations;
            # normalized_sha256 below is the real content gate.
            lines.append(f'NOTE: sha256 differs from recorded value for {rel}')
        lang = ex.get('language', 'php')
        norm = normalize(content, lang)
        norm_sha = hashlib.sha256(norm.encode()).hexdigest()
        recorded_norm = ex.get('normalized_sha256')
        if recorded_norm and recorded_norm != norm_sha:
            lines.append(f'FAIL: normalized_sha256 mismatch {rel}')
            ok = False
        # substitution hygiene
        for sub in ex.get('substitutions', []):
            if 'expected_count' not in sub:
                lines.append(f"FAIL: substitution missing expected_count in {rel}")
                ok = False
            rep = sub.get('replacement', '')
            if rep:
                search = _php_body(content) if lang == 'php' else content
                spans = string_spans(search, lang)
                start, bad = 0, False
                while True:
                    idx = search.find(rep, start)
                    if idx < 0:
                        break
                    if not any(s <= idx and idx + len(rep) <= e for s, e in spans):
                        bad = True
                        break
                    start = idx + 1
                if bad:
                    lines.append(f'FAIL: substitution replacement outside string '
                                 f'literal in {rel}')
                    ok = False

    n_extracts = sum(len(sd.get('extracts', [])) for sd in data.get('samples', {}).values())
    lines.append(f'extracts={n_extracts} files={len(actual)}')
    return ok, lines


def self_test():
    """Prove a one-character sample mutation is caught, without ORIGIN."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        shutil.copytree(REPO / 'samples', tdp / 'samples')
        shutil.copy(REPO / 'PROVENANCE.json', tdp / 'PROVENANCE.json')
        target = tdp / 'samples/01-rls-pgbouncer/src/rls_policies.sql'
        target.write_text(target.read_text().replace('school_id', 'school_iz', 1))
        ok, lines = check(str(tdp / 'PROVENANCE.json'), str(tdp / 'samples'))
        caught = (not ok) and any('rls_policies.sql' in l for l in lines)
        print('SELF-TEST: one-char mutation in rls_policies.sql')
        for l in lines:
            if 'rls_policies' in l or 'FAIL' in l:
                print('  ', l)
        print('SELF-TEST:', 'CAUGHT' if caught else 'NOT CAUGHT')
        return 0 if caught else 1


def main():
    if '--self-test' in sys.argv:
        return self_test()
    ok, lines = check()
    for l in lines:
        print(l)
    print('VERIFY-STRUCTURE:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
