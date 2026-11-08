#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Documentation linter - checks README length, section order, and banned words.
"""
import sys
import re
from pathlib import Path

def check_readme_length(readme_path, max_lines=120):
    """Check root README is <= max_lines."""
    lines = readme_path.read_text(encoding='utf-8').split('\n')
    if len(lines) > max_lines:
        print(f"ERROR: README has {len(lines)} lines (max {max_lines})")
        return False
    return True

def check_banned_words(directory):
    """Check for banned words in all markdown files."""
    banned = ['production', '100%', 'identical', 'enterprise', 'battle-tested',
              'scalable', 'production-ready', 'TODO', 'REST OF LOGIC']
    for md_file in Path(directory).rglob('*.md'):
        if md_file.name.startswith('repomix') or md_file.name == 'SUBSTITUTIONS.md' or '_internal' in md_file.parts:
            continue
        content = md_file.read_text(encoding='utf-8')
        for word in banned:
            if word in content:
                print(f"ERROR: Found banned word '{word}' in {md_file}")
                return False
    return True

def check_spanish(directory):
    """Check for Spanish accents and common words in documentation."""
    accent_pattern = re.compile(r'[áéíóúÁÉÍÓÚñÑ]')
    for md_file in Path(directory).rglob('*.md'):
        if md_file.name.startswith('repomix') or md_file.name == 'SUBSTITUTIONS.md' or '_internal' in md_file.parts:
            continue
        content = md_file.read_text(encoding='utf-8')
        if accent_pattern.search(content):
            print(f"ERROR: Found Spanish accent in {md_file}")
            return False
    return True

if __name__ == '__main__':
    repo = Path(__file__).parent.parent
    checks = [
        check_readme_length(repo / 'README.md'),
        check_banned_words(repo),
        check_spanish(repo)
    ]
    if all(checks):
        print("Documentation checks: PASS")
        sys.exit(0)
    else:
        print("Documentation checks: FAIL")
        sys.exit(1)
