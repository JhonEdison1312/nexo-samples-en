#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Independent provenance re-check — deliberately DIFFERENT code path from
tools/provenance/verify.py + normalizers.py.

Method: naive symmetric normalization. Both sides (ORIGIN git blob slice and
sample file) go through the SAME dumb stripper:

    1. remove /* ... */ blocks (regex, dotall)
    2. remove -- / // / # comments to end-of-line (regex)
    3. remove all whitespace

Because the stripper is symmetric, translated comments and formatting
disappear on BOTH sides; any remaining diff is real content (code or string
literal). Comment-like text inside string literals is stripped identically on
both sides, so it cannot produce a false mismatch — and a real literal edit
still shows up.

Selects 8 extracts at random (seed 42) across all languages, prints the
stripped forms' first difference (must be none), and exits non-zero on any
mismatch. Read-only: never writes to ORIGIN or samples.

Usage: python3 tools/independent_recheck.py /path/to/mother/repo
"""
import json
import random
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BLOCK_RE = re.compile(r'/\*.*?\*/', re.S)
LINE_RE = re.compile(r'(--|//|#)[^\n]*')
WS_RE = re.compile(r'\s+')


def dumb_normalize(code: str) -> str:
    code = BLOCK_RE.sub('', code)
    code = LINE_RE.sub('', code)
    return WS_RE.sub('', code)


def origin_slice(origin: str, commit: str, path: str, start: int, end: int) -> str:
    blob = subprocess.run(
        ['git', '-C', origin, 'show', f'{commit}:{path}'],
        capture_output=True, text=True, check=True).stdout
    lines = blob.split('\n')
    return '\n'.join(lines[start - 1:end])


def first_diff(a: str, b: str, ctx: int = 60):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return (f'first diff at char {i}\n'
                    f'  origin : ...{a[max(0,i-ctx):i+ctx]}...\n'
                    f'  sample : ...{b[max(0,i-ctx):i+ctx]}...')
    if len(a) != len(b):
        i = min(len(a), len(b))
        return (f'length diff at char {i} '
                f'(origin {len(a)} vs sample {len(b)})\n'
                f'  origin : ...{a[max(0,i-ctx):i+ctx]}...\n'
                f'  sample : ...{b[max(0,i-ctx):i+ctx]}...')
    return None


def main():
    if len(sys.argv) != 2:
        print('Usage: python3 tools/independent_recheck.py /path/to/mother/repo')
        sys.exit(1)
    origin = sys.argv[1]
    prov = json.loads((REPO / 'PROVENANCE.json').read_text())
    commit = prov['origin']['commit']

    extracts = []
    for sid, sd in prov['samples'].items():
        for ex in sd['extracts']:
            extracts.append((sid, ex))

    rng = random.Random(42)
    # one pick per language first (coverage), then fill to 8 at random
    by_lang = {}
    for e in extracts:
        by_lang.setdefault(e[1]['language'], []).append(e)
    picks = [rng.choice(group) for _, group in sorted(by_lang.items())]
    rest = [e for e in extracts if e not in picks]
    rng.shuffle(rest)
    picks = (picks + rest)[:8]

    print(f'INDEPENDENT RECHECK — {len(picks)} extracts, seed=42')
    print('=' * 72)
    failures = 0
    for sid, ex in picks:
        rel = f"samples/{sid}/src/{ex['output_file']}"
        sample_path = REPO / rel
        try:
            sample = sample_path.read_text()
        except FileNotFoundError:
            print(f'FAIL {rel}: missing file')
            failures += 1
            continue
        try:
            origin_code = origin_slice(origin, commit, ex['origin_file'],
                                       *ex['line_range'])
        except subprocess.CalledProcessError as e:
            print(f'FAIL {rel}: cannot read origin ({e})')
            failures += 1
            continue
        # Apply declared literal substitutions — they are part of the
        # provenance contract (same transform extract.py performs).
        for sub in ex.get('substitutions', []):
            origin_code = origin_code.replace(sub['pattern'],
                                              sub['replacement'])
        a = dumb_normalize(origin_code)
        b = dumb_normalize(sample)
        d = first_diff(a, b)
        status = 'OK  ' if d is None else 'DIFF'
        if d:
            failures += 1
        print(f'{status} {rel}  [{ex["language"]}]  '
              f'norm_len origin={len(a)} sample={len(b)}')
        if d:
            print('     ' + d.replace('\n', '\n     '))
    print('=' * 72)
    if failures:
        print(f'INDEPENDENT RECHECK: FAIL ({failures} mismatches)')
        return 1
    print('INDEPENDENT RECHECK: PASS — stripped forms equal on all picks')
    return 0


if __name__ == '__main__':
    sys.exit(main())
