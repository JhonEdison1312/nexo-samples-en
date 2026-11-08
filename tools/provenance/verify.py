#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Verify that extracts match origin after transformations.
READ-ONLY: never modifies any tracked file; only reads.

Usage: python3 verify.py /path/to/mother/repo
"""
import sys
import json
import hashlib
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizers import normalize, string_spans, _php_body  # noqa: E402


def git(origin, *args):
    return subprocess.run(
        ['git', '-C', str(origin), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def check_origin_commit_exists(origin_path, expected_commit):
    try:
        kind = git(origin_path, 'cat-file', '-t', expected_commit).strip()
    except subprocess.CalledProcessError:
        print(f"FAIL: Unknown origin commit: {expected_commit}")
        return False
    if kind != 'commit':
        print(f"FAIL: Expected commit {expected_commit} is not a commit object")
        return False
    return True


def substitution_scope_ok(pattern, replacement, slice_text, lang):
    """Every occurrence of `pattern` and of `replacement` in the slice must
    sit inside a string literal. Returns (ok, message)."""
    if lang == 'php':
        search_text = _php_body(slice_text)
    else:
        search_text = slice_text
    spans = string_spans(search_text, lang)

    def count_inside(needle):
        start, count = 0, 0
        while True:
            idx = search_text.find(needle, start)
            if idx < 0:
                return count
            if not any(s <= idx and idx + len(needle) <= e for s, e in spans):
                return -1
            count += 1
            start = idx + 1

    n_pat = count_inside(pattern)
    if n_pat < 0:
        return False, f"pattern '{pattern}' occurs outside a string literal"
    n_rep = count_inside(replacement)
    if n_rep < 0:
        return False, f"replacement '{replacement}' occurs outside a string literal"
    return True, ""


def verify_provenance(origin_path, provenance_file):
    origin = Path(origin_path)
    if not origin.exists():
        print(f"ERROR: Origin path does not exist: {origin_path}")
        return 1

    with open(provenance_file, 'r', encoding='utf-8') as f:
        provenance = json.load(f)

    expected_commit = provenance.get('origin', {}).get('commit')
    if not expected_commit or not check_origin_commit_exists(origin, expected_commit):
        print("Origin commit validation: FAIL")
        return 1
    print(f"Origin commit check PASS (commit: {expected_commit[:16]}...)")

    # ORIGIN HEAD vs recorded commit: report match or mismatch (never fail on
    # mismatch alone — the recorded commit is what extracts are pinned to).
    try:
        head = git(origin, 'rev-parse', 'HEAD').strip()
        if head == expected_commit:
            print(f"ORIGIN HEAD matches recorded commit ({head[:12]}...)")
        else:
            print(f"NOTICE: ORIGIN HEAD ({head[:12]}...) differs from recorded "
                  f"commit ({expected_commit[:12]}...); extracts verified "
                  f"against the recorded commit.")
    except subprocess.CalledProcessError:
        print("NOTICE: could not resolve ORIGIN HEAD")

    # ORIGIN tree state: verify must never write to ORIGIN. We snapshot
    # `git status --porcelain` before and after and require it unchanged.
    status_before = git(origin, 'status', '--porcelain')
    if status_before.strip():
        print("NOTICE: ORIGIN working tree is not clean before verify:")
        for line in status_before.strip().split('\n')[:10]:
            print(f"    {line}")

    all_pass = True

    # Orphan check, both directions
    prov_files = set()
    for sample_id, sample_data in provenance.get('samples', {}).items():
        for extract in sample_data.get('extracts', []):
            prov_files.add(f"samples/{sample_id}/src/{extract['output_file']}")
    actual_files = {str(f) for f in Path('samples').glob('*/src/**/*') if f.is_file()}
    for f in sorted(actual_files - prov_files):
        print(f"FAIL: extra file in src/ not in PROVENANCE.json: {f}")
        all_pass = False
    for f in sorted(prov_files - actual_files):
        print(f"FAIL: PROVENANCE.json entry without file: {f}")
        all_pass = False

    for sample_id, sample_data in provenance.get('samples', {}).items():
        for extract in sample_data.get('extracts', []):
            rel = f"samples/{sample_id}/src/{extract['output_file']}"
            try:
                origin_full = git(origin, 'show',
                                  f"{expected_commit}:{extract['origin_file']}")
            except subprocess.CalledProcessError:
                print(f"FAIL: Cannot read origin file from git blob: {extract['origin_file']}")
                all_pass = False
                continue

            sample_file = Path(rel)
            if not sample_file.exists():
                print(f"FAIL: Sample file not found: {rel}")
                all_pass = False
                continue

            origin_lines = origin_full.split('\n')
            start = extract['line_range'][0] - 1
            end = extract['line_range'][1]
            if start < 0 or end > len(origin_lines) or start >= end:
                print(f"FAIL: Invalid line range {extract['line_range']} for "
                      f"{extract['origin_file']} (file has {len(origin_lines)} lines)")
                all_pass = False
                continue

            origin_slice = '\n'.join(origin_lines[start:end])

            # Apply and independently recount substitutions
            modified_slice = origin_slice
            for sub in extract.get('substitutions', []):
                pattern = sub.get('pattern')
                replacement = sub.get('replacement')
                if 'expected_count' not in sub:
                    print(f"FAIL: Substitution missing expected_count: '{pattern}' "
                          f"in {rel}")
                    all_pass = False
                    continue
                actual_count = origin_slice.count(pattern)
                if actual_count == 0:
                    print(f"FAIL: Declared substitution pattern not found in "
                          f"origin slice: '{pattern}' ({rel})")
                    all_pass = False
                    continue
                if actual_count != sub['expected_count']:
                    print(f"FAIL: Substitution count mismatch for '{pattern}': "
                          f"expected {sub['expected_count']}, got {actual_count} ({rel})")
                    all_pass = False
                    continue
                ok_scope, scope_msg = substitution_scope_ok(
                    pattern, replacement, origin_slice, extract.get('language', 'php'))
                if not ok_scope:
                    print(f"FAIL: Substitution touches non-literal text: {scope_msg} ({rel})")
                    all_pass = False
                    continue
                modified_slice = modified_slice.replace(pattern, replacement)

            lang = extract.get('language', 'php')
            sample_content = sample_file.read_text(encoding='utf-8')

            try:
                norm_origin = normalize(modified_slice, lang)
                norm_sample = normalize(sample_content, lang)
            except Exception as e:
                print(f"FAIL: normalization error for {rel}: {e}")
                all_pass = False
                continue

            sha_normalized = hashlib.sha256(norm_origin.encode()).hexdigest()
            sha_sample_norm = hashlib.sha256(norm_sample.encode()).hexdigest()
            sha_sample_raw = hashlib.sha256(sample_content.encode()).hexdigest()

            if norm_origin == norm_sample:
                recorded = extract.get('sha256')
                rec_note = ''
                if recorded and recorded != sha_sample_raw:
                    # Informational only: comments/whitespace may legitimately
                    # differ (declared comment_translations); normalized_sha256
                    # is the content gate. A raw-hash mismatch is NOT a failure.
                    rec_note = f"  (WARN: recorded sha256 {recorded[:12]}... != file {sha_sample_raw[:12]}...)"
                print(f"PASS: {rel}")
                print(f"      normalized_sha256: {sha_normalized[:16]}...{rec_note}")
            else:
                print(f"FAIL: {rel} does not match origin")
                all_pass = False

    status_after = git(origin, 'status', '--porcelain')
    if status_after != status_before:
        print("FAIL: ORIGIN working tree changed during verify (verify must be read-only)")
        all_pass = False
    else:
        print("ORIGIN tree unchanged by verify (read-only confirmed)")

    if all_pass:
        print("\nAll provenance checks: PASS")
        return 0
    print("\nProvenance checks: FAIL")
    return 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 verify.py /path/to/mother/repo")
        sys.exit(1)
    provenance_file = Path('PROVENANCE.json')
    if not provenance_file.exists():
        print("ERROR: PROVENANCE.json not found")
        sys.exit(1)
    sys.exit(verify_provenance(sys.argv[1], provenance_file))
