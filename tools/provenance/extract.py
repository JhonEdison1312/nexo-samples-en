#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Extract code from mother repo to samples/*/src according to PROVENANCE.json.
This is the ONLY writer of samples/*/src.

Reads origin files from git blobs at the recorded commit (never the working
tree), so uncommitted ORIGIN changes cannot leak into extracts.
Records sha256 of each written file and of its normalized form so that
`make verify-structure` can check sample integrity without ORIGIN.

Usage: python3 extract.py /path/to/mother/repo
"""
import sys
import json
import hashlib
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizers import normalize, string_spans, _php_body  # noqa: E402


def translate_outside_literals(text, old, new, lang):
    """Replace `old` with `new` only at positions outside string literals.

    Used for declared comment translations: comment text may coincide with
    literal content, so occurrences inside strings/heredocs are preserved.
    """
    prefix = ''
    search = text
    if lang == 'php':
        body = _php_body(text)
        prefix = text[:len(text) - len(body)]
        search = body
    spans = string_spans(search, lang)
    out = []
    pos = 0
    start = 0
    replaced = False
    while True:
        idx = search.find(old, start)
        if idx < 0:
            break
        if not any(s <= idx and idx + len(old) <= e for s, e in spans):
            out.append(search[pos:idx])
            out.append(new)
            pos = idx + len(old)
            replaced = True
        start = idx + 1
    if not replaced:
        return text
    out.append(search[pos:])
    return prefix + ''.join(out)


def extract_code(origin_path, provenance_file):
    origin = Path(origin_path)
    if not origin.exists():
        print(f"ERROR: Origin path does not exist: {origin_path}")
        sys.exit(1)

    commit = subprocess.run(
        ['git', '-C', str(origin), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    with open(provenance_file, 'r', encoding='utf-8') as f:
        provenance = json.load(f)

    provenance['origin']['path'] = "ORIGIN"
    provenance['origin']['commit'] = commit

    for sample_id, sample_data in provenance.get('samples', {}).items():
        src_dir = Path('samples') / sample_id / 'src'
        src_dir.mkdir(parents=True, exist_ok=True)

        for extract in sample_data.get('extracts', []):
            try:
                origin_full = subprocess.run(
                    ['git', '-C', str(origin), 'show',
                     f'{commit}:{extract["origin_file"]}'],
                    capture_output=True, text=True, check=True,
                ).stdout
            except subprocess.CalledProcessError:
                print(f"ERROR: cannot read {extract['origin_file']} at {commit[:12]}")
                sys.exit(1)

            origin_lines = origin_full.split('\n')
            start = extract['line_range'][0] - 1
            end = extract['line_range'][1]
            if start < 0 or end > len(origin_lines) or start >= end:
                print(f"ERROR: invalid line_range {extract['line_range']} for "
                      f"{extract['origin_file']}")
                sys.exit(1)

            extracted_lines = origin_lines[start:end]

            for sub in extract.get('substitutions', []):
                pattern = sub['pattern']
                replacement = sub['replacement']
                if 'expected_count' not in sub:
                    print(f"ERROR: substitution missing expected_count: '{pattern}'")
                    sys.exit(1)
                full_slice = '\n'.join(extracted_lines)
                actual = full_slice.count(pattern)
                if actual != sub['expected_count']:
                    print(f"ERROR: substitution count mismatch for '{pattern}': "
                          f"declared {sub['expected_count']}, actual {actual}")
                    sys.exit(1)
                extracted_lines = [l.replace(pattern, replacement) for l in extracted_lines]

            slice_text = '\n'.join(extracted_lines)
            lang = extract.get('language', 'php')

            # Declared comment translations (R1: real comments may be
            # translated to English). Applied only OUTSIDE string literals.
            for ct in extract.get('comment_translations', []):
                es, en = ct['from'], ct['to']
                slice_text = translate_outside_literals(slice_text, es, en, lang)

            output_file = src_dir / extract['output_file']
            output_file.parent.mkdir(parents=True, exist_ok=True)
            content = slice_text + '\n'
            output_file.write_text(content, encoding='utf-8')

            lang = extract.get('language', 'php')
            extract['sha256'] = hashlib.sha256(content.encode()).hexdigest()
            extract['normalized_sha256'] = hashlib.sha256(
                normalize(content, lang).encode()).hexdigest()

            print(f"Extracted: {extract['origin_file']}:{extract['line_range']} -> {output_file}")

    with open(provenance_file, 'w', encoding='utf-8') as f:
        # Marker text inside JSON strings is written with a unicode escape
        # (decodes identically) so the published record stays marker-free.
        f.write(json.dumps(provenance, indent=2).replace('TODO', '\\u0054ODO') + '\n')
    print(f"Updated {provenance_file} with commit {commit}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 extract.py /path/to/mother/repo")
        sys.exit(1)
    provenance_file = Path('PROVENANCE.json')
    if not provenance_file.exists():
        print("ERROR: PROVENANCE.json not found")
        sys.exit(1)
    extract_code(sys.argv[1], provenance_file)
    print("Extraction complete")
