#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Demo output regression check.

Runs each sample's test target, normalizes volatile bits (timestamps, UUIDs,
nonces, PIDs, timings), and diffs against samples/NN/EXPECTED_OUTPUT.txt.

Usage:
  python3 tools/check_demo_output.py            # compare mode (exit 1 on diff)
  python3 tools/check_demo_output.py --update   # regenerate EXPECTED_OUTPUT.txt
Env must be up (tools/env/up.sh) for DB/Redis samples.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ANSI = re.compile(r'\x1b\[[0-9;]*m')
TS = re.compile(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\]')
UUID = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')
NONCE = re.compile(r'nonce-[A-Za-z0-9-]+')
ELAPSED = re.compile(r'\b\d+(?:\.\d+)?\s?(?:ms|s)\b(?=\s|$)')
PID = re.compile(r'\bpid[:= ]+\d+\b', re.I)


def normalize(text, sample):
    text = ANSI.sub('', text)
    text = TS.sub('[TS]', text)
    text = NONCE.sub('<NONCE>', text)
    if sample in ('02-audit-chain',):
        text = UUID.sub('<UUID>', text)
    if sample == '03-edge-pipeline':
        text = re.sub(r'uuid-\d{10,}', '<UUIDTS>', text)
        # build step is not demo output; appears only when the binary is stale
        text = '\n'.join(l for l in text.split('\n')
                         if l.strip() != 'Compiling edge_demo...') + '\n'
    # recursive-make wrapper noise (locale-dependent): 'make[N]: ... directory'"
    text = re.sub(r'^make\[\d+\]:.*(directorio|directory).*$', '',
                  text, flags=re.M)
    text = ELAPSED.sub('<T>', text)
    text = PID.sub('pid=<PID>', text)
    # trailing whitespace / blank-line runs
    lines = [l.rstrip() for l in text.split('\n')]
    out, blank = [], False
    for l in lines:
        if l == '':
            if not blank:
                out.append('')
            blank = True
        else:
            out.append(l)
            blank = False
    return '\n'.join(out).strip('\n') + '\n'


SAMPLES = {
    '01-rls-pgbouncer': 'make test-01',
    '02-audit-chain': 'make test-02',
    '03-edge-pipeline': 'make test-03',
    '04-nodus-parser': 'make test-04',
    '05-redis-reliable-queue': 'make test-05',
    '06-table-partitioning': 'make test-06',
}


def run_sample(cmd):
    p = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    update = '--update' in sys.argv
    results = []
    for sid, cmd in SAMPLES.items():
        code, out = run_sample(cmd)
        norm = normalize(out, sid)
        exp_path = REPO / f'samples/{sid}/EXPECTED_OUTPUT.txt'
        if update:
            exp_path.write_text(norm)
            print(f'UPDATED samples/{sid}/EXPECTED_OUTPUT.txt '
                  f'(exit={code}, {len(norm.splitlines())} lines)')
            results.append((sid, 'UPDATED', code == 0))
            continue
        if code != 0:
            print(f'FAIL {sid}: test command exited {code}')
            results.append((sid, 'FAIL(run)', False))
            continue
        expected = exp_path.read_text() if exp_path.exists() else ''
        if norm == expected:
            print(f'PASS {sid}: output matches EXPECTED_OUTPUT.txt')
            results.append((sid, 'PASS', True))
        else:
            import difflib
            diff = list(difflib.unified_diff(
                expected.split('\n'), norm.split('\n'),
                'expected', 'actual', lineterm=''))[:30]
            print(f'DIFF {sid}: output differs from EXPECTED_OUTPUT.txt')
            for l in diff:
                print('   ' + l)
            results.append((sid, 'DIFF', False))
    ok = all(r[2] for r in results)
    print('DEMO OUTPUT CHECK:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
