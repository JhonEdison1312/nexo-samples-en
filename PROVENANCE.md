# Provenance Methodology

This document describes how code extracts are tracked from the mother NEXO
repository to this public samples repository.

## Extraction Process

1. Source is read from **git blobs** at the commit recorded in
   `PROVENANCE.json` (`origin.commit`), never from the working tree. This
   makes verification reproducible even if ORIGIN's checkout moves.

2. A contiguous line range is sliced from the blob (`line_range: [start, end]`).
3. Only two transformation kinds are permitted, and both must be declared
   per extract:
   - `substitutions` — literal replacements inside **string literals only**,
     each with a mandatory `expected_count` that is independently recounted.
   - `comment_translations` — `{from, to}` pairs applied **outside** string
     literals, used to translate ORIGIN's Spanish comments to English.

4. `extract.py` writes the final file and records `sha256` (raw bytes) and
     `normalized_sha256` (comments/whitespace stripped, literals verbatim)
     per extract.

## Verification

`tools/provenance/verify.py` (requires ORIGIN path):

- Validates the recorded ORIGIN commit exists and reports HEAD vs recorded.
- Orphan check in both directions (`samples/*/src` vs PROVENANCE entries).
- Recounts substitution occurrences and enforces `expected_count`.
- Verifies every substitution pattern/replacement sits inside a string
  literal (real tokenizers: `token_get_all` for PHP, literal-aware scanners
  for SQL/C++/shell).

- Normalizes origin slice and sample with the same tokenizer and compares;
  string literals are compared **verbatim**.

- Confirms ORIGIN's working tree is unchanged after the run (read-only).

`tools/verify_structure.py` performs the same integrity checks **without**
ORIGIN (hashes + orphans + substitution hygiene) and has a `--self-test`
mode that proves a one-character mutation is caught.

`tools/mutation_tests.py` runs 18 mutation cases (code edits in all four
languages, shifted ranges, removed/undeclared/wrong-count substitutions,
unknown commit, orphan files, missing files, literal edits, plus comment and
whitespace negative controls). All must be detected; controls must pass.

`tools/independent_recheck.py` re-checks 8 random extracts (seed 42, one per
language) with a deliberately different, naive symmetric stripper.

## Normalization Rules

- **PHP**: `token_get_all`; `T_WHITESPACE`, `T_COMMENT`, `T_DOC_COMMENT`
  dropped; everything else (including string literal contents) kept verbatim.

- **SQL**: line (`--`) and block (`/* */`, nestable) comments removed;
  single/double-quoted strings, dollar-quoted bodies (`$$...$$`, `$tag$...$tag$`)
  and escaped quotes preserved.

- **C++**: `//` and `/* */` comments removed; strings, char literals and
  raw strings (`R"delim(...)delim"`) preserved.

- **Shell**: `#` comments removed outside quotes; single/double quotes and
  heredocs preserved.

- Whitespace is insignificant everywhere; string literal **contents** are
  significant everywhere.

## Stubs (ADDED FOR THIS SAMPLE)

Glue code lives in `samples/*/harness/` or `tools/`; every stub file begins
with the marker `ADDED FOR THIS SAMPLE` (or is listed here). Notable glue:

- `tools/env/up.sh`, `tools/env/down.sh` — user-space PostgreSQL 18 +
  PgBouncer + Redis lifecycle (no sudo required).

- `samples/*/harness/` — per-sample runners, seeds, Dockerfiles, compose.
- `samples/03-edge-pipeline/harness/include/nlohmann/json.hpp` — vendored
  single-header JSON library (MIT).

- `samples/03-edge-pipeline/harness/main_demo.cpp` — demo driver.
- `tools/*` — verification, mutation, language, docs and release tooling.
- `.github/workflows/ci.yml`, root `Makefile`.

## Extracted vs Added LOC

Extracted LOC = sum of declared `line_range` lengths in PROVENANCE.json.

| Sample | Extracts | Extracted LOC | Harness LOC (approx) |
|--------|----------|---------------|----------------------|
| 01-rls-pgbouncer | 2 | 74 | ~235 |
| 02-audit-chain | 2 | 215 | ~177 |
| 03-edge-pipeline | 20 | 2283 | ~290 |
| 04-nodus-parser | 1 | 572 | ~200 |
| 05-redis-reliable-queue | 1 | 220 | ~200 |
| 06-table-partitioning | 3 | 124 | ~122 |
| **Total** | **29** | **3488** | **~1224** |

## Known Limitations

- The samples repository is currently nested inside ORIGIN as a gitlink
  (`nexo-samples-en` mode 160000). Relocation outside ORIGIN is a pending
  human action; verification does not depend on the nesting.

- Comment translations are declared but not semantically verified beyond
  the normalizer ignoring comments — reviewers should spot-check
  `PROVENANCE.json` `comment_translations` entries.
