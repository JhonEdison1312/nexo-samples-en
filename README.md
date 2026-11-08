# NEXO Samples - README

![CI](https://github.com/JhonEdison1312/nexo-samples-en/actions/workflows/ci.yml/badge.svg)

> Landing: <https://nexo-u2nb.vercel.app>
> Live demo (functional app): <https://nexo-eight-xi.vercel.app>

Welcome! This repository contains sanitized extracts from NEXO, a prototype I built as sole backend engineer. It is published as a technical portfolio for interviews and learning. NEXO itself remains proprietary, but you're welcome to read, run, discuss and critique the patterns shown here. See LICENSE for exact terms.

## What This Is / What This Is Not

**This is:**

- Sanitized extracts from my NEXO prototype (real code from the actual system)
- Test harnesses added to make the extracts runnable as standalone demos
- Demonstrations of architectural patterns I implemented
- Small, focused samples that demonstrate individual patterns

**This is NOT:**

- The complete NEXO codebase
- A full application (each sample demonstrates a specific pattern, not a complete system)
- Production code (NEXO is in prototype stage, simulators only, no real users)
- Code written just for samples (everything under samples/*/src is extracted from the real system; harness code is added glue)

## Featured Samples

**1. RLS + PgBouncer + SET LOCAL** (~5 min)

- PostgreSQL Row-Level Security with transaction pooling to prevent cross-tenant context leaks
- Run: `make up && make test-01`

**2. HMAC Audit Chain** (~5 min)

- Tamper-evident audit logs with hash-chained HMAC-SHA256
- Run: `make up && make test-02`

**3. Edge Pipeline** (15+ min)

- C++20 offline-first node with hardware abstraction, SQLite, AES-256-GCM encryption, and cloud sync
- Run: `make up && make test-03`

**4. Nodus LLM Parser** (15+ min)

- LLM integration with guardrails - parser classifies intents, composer rewrites responses with strict validation, system degrades safely without model
- Run: `make test-04`

## All Samples Index

| Sample | Skill Demonstrated | Area | Run |
|--------|-------------------|------|-----|
| 01-rls-pgbouncer | Multi-tenant SQL with RLS + PgBouncer + SET LOCAL | Authentication | `make up && make test-01` |
| 02-audit-chain | HMAC audit chain for tamper evidence | Security | `make up && make test-02` |
| 03-edge-pipeline | C++20 offline-first architecture with encryption | Edge | `make up && make test-03` |
| 04-nodus-parser | LLM integration with guardrails and deterministic fallback | AI Integration | `make test-04` |
| 05-redis-reliable-queue | Atomic Lua LMOVE queue with GC and DLQ | Async Workers | `make up && make test-05` |
| 06-table-partitioning | Monthly RANGE partition lifecycle with retention | Database | `make up && make test-06` |

## System Map

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the complete architecture diagram and data flow.

## How Authenticity Is Verified

Every extract is tracked in PROVENANCE.json with origin path, line range, and transformations. Run `make verify-provenance ORIGIN=/path/to/mother/repo` to verify that sample code matches the mother repository after declared substitutions. See PROVENANCE.md for details.

## Run Everything

**Prerequisites:**
Run `make deps-check` to verify all required tools are installed.

**Start environment:**

```bash
make up

```

**Run individual samples:**

```bash
make test-01  # RLS + PgBouncer
make test-02  # HMAC Audit Chain
make test-03  # Edge Pipeline
make test-04  # Nodus Parser
make test-05  # Redis Queue
make test-06  # Table Partitioning

```

**Stop environment:**

```bash
make down

```

**Verify provenance (requires ORIGIN repository):**

```bash
make verify ORIGIN=/path/to/mother/repo

```

## License

This repository is licensed under the PolyForm Noncommercial 1.0.0 License - see LICENSE file for the full text.
