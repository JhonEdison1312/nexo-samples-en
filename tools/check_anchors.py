#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Documentation anchor check (CI-safe, no ORIGIN needed).

Verifies:
  1. Root README <= 120 lines; each sample README <= 80 lines.
  2. Every `make test-NN` / `make up` / `make down` mentioned in READMEs
     exists as a Makefile target.
  3. Every samples/NN-*/ path referenced in READMES/docs exists on disk.
  4. Sample READMEs contain the required sections (Purpose, Run it,
     Limitations).
  5. docs/ARCHITECTURE.md contains a mermaid block.
  6. LICENSE exists and mentions PolyForm Noncommercial.
  7. docs/CLAIMS.md exists and references all six samples.

Usage: python3 tools/check_anchors.py
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
failures = []


def fail(msg):
    failures.append(msg)
    print(f'FAIL: {msg}')


def ok(msg):
    print(f'PASS: {msg}')


# 1. line limits
root = (REPO / 'README.md').read_text()
n = len(root.split('\n'))
if n <= 121:
    ok(f'root README {n} lines (<=120 content)')
else:
    fail(f'root README {n} lines > 120')

sample_dirs = sorted((REPO / 'samples').iterdir())
for sd in sample_dirs:
    rm = sd / 'README.md'
    if not rm.exists():
        fail(f'{sd.name}: missing README.md')
        continue
    lines = len(rm.read_text().split('\n'))
    if lines <= 81:
        ok(f'{sd.name}/README.md {lines} lines')
    else:
        fail(f'{sd.name}/README.md {lines} lines > 80')

# 2. make targets
mk = (REPO / 'Makefile').read_text()
targets = set(re.findall(r'^([A-Za-z0-9_-]+)\s*:', mk, re.M))
readmes = [REPO / 'README.md'] + [sd / 'README.md' for sd in sample_dirs]
for rm in readmes:
    if not rm.exists():
        continue
    text = rm.read_text()
    for m in re.finditer(r'`make ([a-z0-9-]+)', text):
        t = m.group(1)
        if t not in targets:
            fail(f'{rm.relative_to(REPO)}: `make {t}` not a Makefile target')
        else:
            ok(f'`make {t}` referenced in {rm.name}')

# 3. referenced sample paths exist
for rm in readmes + [REPO / 'docs/ARCHITECTURE.md', REPO / 'docs/CLAIMS.md']:
    if not rm.exists():
        continue
    text = rm.read_text()
    for m in re.finditer(r'`?((?:samples|tools|docs)/[A-Za-z0-9_./-]+)`?', text):
        p = m.group(1).rstrip('.,')
        # strip line-range suffixes like file.php:10-20
        p = re.sub(r':\d+(-\d+)?$', '', p)
        if '*' in p:
            continue
        if not (REPO / p).exists():
            # try as directory prefix
            if not list(REPO.glob(p + '*')):
                fail(f'{rm.relative_to(REPO)}: referenced path missing: {p}')

# 4. required sections in sample READMEs
for sd in sample_dirs:
    rm = sd / 'README.md'
    if not rm.exists():
        continue
    text = rm.read_text().lower()
    for section in ('purpose', 'run it', 'limitation'):
        if section not in text:
            fail(f'{sd.name}/README.md: missing section ~{section}')

# 5. mermaid
arch = REPO / 'docs/ARCHITECTURE.md'
if arch.exists() and '```mermaid' in arch.read_text():
    ok('docs/ARCHITECTURE.md has mermaid diagram')
else:
    fail('docs/ARCHITECTURE.md missing mermaid block')

# 6. LICENSE
lic = REPO / 'LICENSE'
if lic.exists() and 'PolyForm Noncommercial' in lic.read_text():
    ok('LICENSE mentions PolyForm Noncommercial')
else:
    fail('LICENSE missing or does not mention PolyForm Noncommercial')

# 7. CLAIMS covers all samples
claims = REPO / 'docs/CLAIMS.md'
if claims.exists():
    ctext = claims.read_text()
    for sd in sample_dirs:
        if sd.name.split('-')[0] not in ctext and sd.name not in ctext:
            fail(f'docs/CLAIMS.md does not reference {sd.name}')
    ok('docs/CLAIMS.md references checked')
else:
    fail('docs/CLAIMS.md missing')

print('=' * 60)
if failures:
    print(f'ANCHOR CHECK: FAIL ({len(failures)} problems)')
    sys.exit(1)
print('ANCHOR CHECK: PASS')
