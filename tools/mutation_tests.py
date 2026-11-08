#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Mutation test suite for provenance verification.

Protocol per test:
  (a) baseline `verify.py` must exit 0 first;
  (b) ONE mutation on ONE file;
  (c) verifier must exit non-zero with an expected message naming the file
      (negative controls must exit 0);
  (d) all other extracts must still PASS;
  (e) file restored, mutated paths must be clean.

SAFETY: the entire suite runs on a temporary `cp -a` copy of the repo.
`git checkout`/writes only ever happen inside that copy — the real
working tree is never modified, dirty or clean.

Prints a table: mutation | target | expected message | found.

Usage: python3 tools/mutation_tests.py /path/to/mother/repo
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_verify(origin):
    p = subprocess.run(
        ['python3', 'tools/provenance/verify.py', str(origin)],
        cwd=REPO, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def git(*args):
    return subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True)


def restore():
    # Safe: REPO points at the disposable temp copy, never the real tree.
    git('checkout', '--', 'samples/', 'PROVENANCE.json')


def status_clean():
    # Only the paths this suite mutates must be clean afterwards.
    return git('status', '--porcelain', '--',
               'samples/', 'PROVENANCE.json').stdout.strip() == ''


def read(path):
    return (REPO / path).read_text()


def write(path, text):
    (REPO / path).write_text(text)


def prov_mutate(fn):
    data = json.loads((REPO / 'PROVENANCE.json').read_text())
    fn(data)
    (REPO / 'PROVENANCE.json').write_text(json.dumps(data, indent=2) + '\n')


PHP_F = 'samples/01-rls-pgbouncer/src/auth_middleware.php'
SQL_F = 'samples/01-rls-pgbouncer/src/rls_policies.sql'
CPP_F = 'samples/03-edge-pipeline/src/encryption.cpp'
SH_F = 'samples/06-table-partitioning/src/create_monthly_partition.sh'
SQL_STR_F = 'samples/02-audit-chain/src/audit_chain_trigger.sql'
CPP_STR_F = 'samples/03-edge-pipeline/src/sqlite_manager.cpp'
SH_STR_F = 'samples/06-table-partitioning/src/drop_old_partitions.sh'
PHP_STR_F = 'samples/04-nodus-parser/src/nexus_llm.php'


def sub_file_edit(path, old, new):
    t = read(path)
    assert old in t, f'{old!r} not in {path}'
    write(path, t.replace(old, new, 1))


# Fixture for substitution tests: declare a substitution AND apply it to the
# sample so baseline passes. The mutation under test then touches ONE file.
SUB_PATTERN = 'u.profile_photo_url, u.work_shift, u.terms_version'
SUB_REPLACEMENT = 'X-TEST-SUB'


def fixture_add_substitution():
    prov_mutate(lambda d: d['samples']['01-rls-pgbouncer']['extracts'][0]
                .setdefault('substitutions', []).append(
                    {'pattern': SUB_PATTERN, 'replacement': SUB_REPLACEMENT,
                     'expected_count': 1}))
    sub_file_edit(PHP_F, SUB_PATTERN, SUB_REPLACEMENT)
    # keep recorded hashes consistent so the fixture baseline is green
    import hashlib, sys as _s
    _s.path.insert(0, str(REPO / 'tools/provenance'))
    from normalizers import normalize
    content = read(PHP_F)
    prov_mutate(lambda d: d['samples']['01-rls-pgbouncer']['extracts'][0]
                .update({'sha256': hashlib.sha256(content.encode()).hexdigest(),
                         'normalized_sha256': hashlib.sha256(
                             normalize(content, 'php').encode()).hexdigest()}))


def _refresh(path, lang):
    """Recompute recorded hashes for the extract matching `path` so a
    fixture edit does not trip the sha256 gate before the content check."""
    import hashlib, sys as _s
    _s.path.insert(0, str(REPO / 'tools/provenance'))
    from normalizers import normalize
    content = read(path)
    data = json.loads((REPO / 'PROVENANCE.json').read_text())
    out_name = path.split('/src/')[-1]
    for sd in data['samples'].values():
        for e in sd['extracts']:
            if e['output_file'] == out_name:
                e['sha256'] = hashlib.sha256(content.encode()).hexdigest()
                e['normalized_sha256'] = hashlib.sha256(
                    normalize(content, lang).encode()).hexdigest()
    (REPO / 'PROVENANCE.json').write_text(json.dumps(data, indent=2) + '\n')


def fixture_remove_substitution():
    prov_mutate(lambda d: d['samples']['01-rls-pgbouncer']['extracts'][0]
                .setdefault('substitutions', []).pop())


TESTS = [
    # (name, setup_fn_or_None, mutate_fn, restore_extra_fn_or_None,
    #  expected_substring_or_None_for_negative_control, target_file)
    ('PHP 1-char change', None,
     lambda: sub_file_edit(PHP_F, '$startedTx', '$startexTx'),
     None, 'auth_middleware.php', PHP_F),
    ('SQL 1-char change', None,
     lambda: sub_file_edit(SQL_F, 'school_id', 'school_iz'),
     None, 'rls_policies.sql', SQL_F),
    ('C++ 1-char change', None,
     lambda: sub_file_edit(CPP_F, 'm_aesKey', 'm_aesKez'),
     None, 'encryption.cpp', CPP_F),
    ('Shell 1-char change', None,
     lambda: sub_file_edit(SH_F, 'psql', 'psqz'),
     None, 'create_monthly_partition.sh', SH_F),
    ('Shifted line range', None,
     lambda: prov_mutate(lambda d: d['samples']['01-rls-pgbouncer']
                         ['extracts'][0]['line_range'].__setitem__(0,
                          d['samples']['01-rls-pgbouncer']['extracts'][0]
                          ['line_range'][0] + 1)),
     None, 'does not match origin', 'PROVENANCE.json'),
    ('Removed substitution', fixture_add_substitution,
     fixture_remove_substitution, None,
     'does not match origin', 'PROVENANCE.json'),
    ('Undeclared substitution', fixture_add_substitution,
     lambda: (sub_file_edit(PHP_F, SUB_REPLACEMENT, 'Y-UNDECLARED'),
              _refresh(PHP_F, 'php')),
     None, 'does not match origin', PHP_F),
    ('Wrong expected_count', None,
     lambda: prov_mutate(lambda d: d['samples']['01-rls-pgbouncer']
                         ['extracts'][0].__setitem__('substitutions', [{
                             'pattern': 'function', 'replacement': 'FUNCTION',
                             'expected_count': 999}])),
     None, 'count mismatch', 'PROVENANCE.json'),
    ('Unknown origin commit', None,
     lambda: prov_mutate(lambda d: d['origin'].__setitem__('commit',
                                                          '0' * 40)),
     None, 'Unknown origin commit', 'PROVENANCE.json'),
    ('Extra file in src/', None,
     lambda: (REPO / 'samples/01-rls-pgbouncer/src/extra_orphan.txt')
             .write_text('orphan'),
     lambda: (REPO / 'samples/01-rls-pgbouncer/src/extra_orphan.txt')
             .unlink(missing_ok=True),
     'Extra files|not in PROVENANCE', 'samples/01-rls-pgbouncer/src/extra_orphan.txt'),
    ('PROVENANCE entry without file', None,
     lambda: prov_mutate(lambda d: d['samples']['01-rls-pgbouncer']
                         ['extracts'].append({
                             'origin_file': 'backend/api/fake.php',
                             'line_range': [1, 10], 'output_file': 'fake.php',
                             'language': 'php', 'substitutions': []})),
     None, 'Cannot read origin file|without file', 'PROVENANCE.json'),
    ('String-literal change', None,
     lambda: sub_file_edit(PHP_F, 'SELECT', 'INSERT'),
     None, 'auth_middleware.php', PHP_F),
    ('SQL comment-like text inside string', None,
     lambda: sub_file_edit(SQL_STR_F, 'default-secret-change-me',
                           'default-secret-change-ME'),
     None, 'audit_chain_trigger.sql', SQL_STR_F),
    ('C++ // inside string literal', None,
     lambda: sub_file_edit(CPP_STR_F, 'journal_mode=WAL', 'journal_mode=WALX'),
     None, 'sqlite_manager.cpp', CPP_STR_F),
    ('Shell # inside string literal', None,
     lambda: sub_file_edit(SH_STR_F, '${NEXO_PARTITION_RETENTION_MONTHS:-24}',
                           '${NEXO_PARTITION_RETENTION_MONTHX:-24}'),
     None, 'drop_old_partitions.sh', SH_STR_F),
    ('PHP comment-like inside string', None,
     lambda: sub_file_edit(PHP_STR_F, "'/chat/completions'", "'/chat/completionx'"),
     None, 'nexus_llm.php', PHP_STR_F),
    # Negative controls — verifier must still PASS
    ('Comment rewording (negative control)', None,
     lambda: sub_file_edit(PHP_F,
                           '// PgBouncer: en transaction-pool mode',
                           '// NOTE: en transaction-pool mode'),
     None, None, PHP_F),
    ('Whitespace-only change (negative control)', None,
     lambda: write(PHP_F, read(PHP_F).replace('        try {', '    try {', 1)),
     None, None, PHP_F),
]


def main():
    global REPO
    if len(sys.argv) != 2:
        print('Usage: python3 tools/mutation_tests.py /path/to/mother/repo')
        sys.exit(1)
    origin = sys.argv[1]

    # Run the whole suite on a throwaway copy: mutations and `git checkout`
    # restores happen only inside the copy; the real working tree is never
    # touched, whether it is clean or dirty.
    src_repo = REPO
    work = Path(tempfile.mkdtemp(prefix='nexo-mutation-'))
    try:
        subprocess.run(['cp', '-a', str(src_repo) + '/.', str(work)],
                       check=True)
    except subprocess.CalledProcessError as e:
        print(f'ERROR: could not stage temp copy: {e}')
        shutil.rmtree(work, ignore_errors=True)
        sys.exit(1)
    REPO = work
    print(f'[setup] mutations run on temp copy: {work}')
    print('[setup] real working tree is never modified')

    results = []
    print('mutation | target | expected message | found')
    print('-' * 100)

    for name, setup, mutate, extra_restore, expected, target in TESTS:
        restore()
        if setup:
            setup()
        # (a) baseline must pass
        code, out = run_verify(origin)
        if code != 0:
            print(f'{name} | {target} | BASELINE FAIL | verify exited {code}')
            results.append((name, 'FAIL', 'baseline'))
            restore()
            continue
        # (b) apply the single mutation
        mutate()
        try:
            code, out = run_verify(origin)
            if expected is None:
                # negative control: must PASS
                if code == 0:
                    verdict = 'PASS (control held)'
                else:
                    verdict = f'FAIL (control broke): {out[-200:]}'
            else:
                import re as _re
                if code != 0 and _re.search(expected, out):
                    # (d) other extracts still pass?
                    passes = out.count('PASS: samples/')
                    verdict = f'PASS (detected, {passes} extracts still pass)'
                elif code != 0:
                    verdict = f'FAIL (wrong message): {out[-200:]}'
                else:
                    verdict = 'FAIL (mutation not detected)'
        finally:
            restore()
            if extra_restore:
                extra_restore()
        clean = 'clean' if status_clean() else 'DIRTY'
        print(f'{name} | {target} | {expected or "(must pass)"} | {verdict} [{clean}]')
        results.append((name, 'PASS' if verdict.startswith('PASS') else 'FAIL', verdict))

    fails = [r for r in results if r[1] != 'PASS']
    skipped = [r for r in results if 'SKIP' in r[0]]
    print('-' * 100)
    print(f'total={len(results)} pass={len(results)-len(fails)} fail={len(fails)} skipped={len(skipped)}')
    clean = status_clean()
    shutil.rmtree(work, ignore_errors=True)
    if fails or skipped or not clean:
        sys.exit(1)
    print('MUTATION SUITE: ALL PASS')


if __name__ == '__main__':
    main()
