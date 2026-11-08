#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Master verifier entry point.

Delegates to tools/release_check.sh which runs gates G1-G8, writes raw logs
to _internal/release/raw/, and only prints ALL GATES PASSED when every gate
genuinely passed. This file exists for backwards compatibility with
`make verify`.

Usage: python3 tools/run_verify.py [/path/to/mother/repo]
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main():
    origin = sys.argv[1] if len(sys.argv) > 1 else ''
    if not origin:
        import os
        origin = os.environ.get('ORIGIN', '')
    if not origin:
        print('ERROR: ORIGIN repo path required (arg or $ORIGIN env);'
              ' no implicit parent-directory fallback')
        return 2
    if not (Path(origin) / '.git').exists():
        print('ERROR: ORIGIN repo path required (arg or $ORIGIN env)')
        return 2
    script = REPO / 'tools' / 'release_check.sh'
    return subprocess.run(['bash', str(script), origin], cwd=REPO).returncode


if __name__ == '__main__':
    sys.exit(main())
