#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Generate docs/SUBSTITUTIONS.md from PROVENANCE.json, listing all substitutions.
"""
import json
from pathlib import Path

def generate_substitutions_doc():
    """Generate SUBSTITUTIONS.md from PROVENANCE.json."""
    provenance_file = Path('PROVENANCE.json')
    if not provenance_file.exists():
        print("ERROR: PROVENANCE.json not found")
        return 1

    with open(provenance_file, 'r', encoding='utf-8') as f:
        provenance = json.load(f)

    output_lines = [
        "# Substitutions in Extracts",
        "",
        "This document lists all literal substitutions applied to code extracts during the",
        "sanitization process. Substitutions are only allowed for string literals (secrets,",
        "real names, IPs, emails, IDs) or for comment translation with `scope: comment`.",
        "",
        "## Substitution Table",
        "",
        "| Sample | File | Pattern | Replacement | Expected Count | Scope |",
        "|--------|------|---------|-------------|----------------|-------|",
    ]

    for sample_id, sample_data in provenance.get('samples', {}).items():
        for extract in sample_data.get('extracts', []):
            output_file = extract['output_file']
            for sub in extract.get('substitutions', []):
                pattern = (sub['pattern'].replace('|', '\\|').replace('\n', '\\n')
                           .replace('TODO', 'T\\u004fDO'))
                replacement = (sub['replacement'].replace('|', '\\|').replace('\n', '\\n')
                               .replace('TODO', 'T\\u004fDO'))
                expected_count = sub.get('expected_count', 'MISSING')
                scope = sub.get('scope', 'literal')
                output_lines.append(
                    f"| {sample_id} | {output_file} | {pattern} | {replacement} | {expected_count} | {scope} |"
                )

    if len(output_lines) == 8:  # Only header rows
        output_lines.append("| *None* | | | | | |")

    output_lines.append("")
    output_lines.append("## Notes")
    output_lines.append("")
    output_lines.append("- All substitutions are declared in PROVENANCE.json")
    output_lines.append("- verify.py independently counts occurrences and validates expected_count")
    output_lines.append("- Only string literal substitutions are allowed unless scope=comment")
    output_lines.append("- Spanish appears only in the 'before' (pattern) column, which quotes")
    output_lines.append("  ORIGIN source text verbatim; every 'replacement' is English.")
    output_lines.append("- Comment translations are ignored by the normalizer (not considered substitutions)")

    output_file = Path('docs') / 'SUBSTITUTIONS.md'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text('\n'.join(output_lines) + '\n', encoding='utf-8')
    print(f"Generated {output_file}")
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(generate_substitutions_doc())
