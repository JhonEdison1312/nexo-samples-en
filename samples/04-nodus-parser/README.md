# Nodus LLM Parser & Guardrails

## Purpose

Demonstrates an LLM integration pipeline with strict guardrails: OpenAI-compatible natural language classification, entity sanitization with domain allowlists, post-generation hallucination detection, and safe deterministic degradation when the model is unavailable.

## Where it fits

NEXO's conversational assistant ("Nodus" in the product UI, implemented in the internal codebase under `backend/api/nexus/`). Nodus translates free-form user questions into validated intent structures without ever executing arbitrary SQL or mutating state.

## Origin

- Path: `backend/api/nexus/nexus_llm.php` (lines 1-572)
- Transformations: 0 substitutions applied (clean code extract matching mother repo commit).

## What to look at

- `nexus_llm.php` (lines 25-44): Configuration and graceful capability checks (`nxLlmEnabled`).
- `nexus_llm.php` (lines 91-155): Network transport via libcurl with 429 Retry-After handling and timeout budget accounting.
- `nexus_llm.php` (lines 190-320): Response Composer and post-generation anti-hallucination guard (`nxLlmComposeGuard`).
- `nexus_llm.php` (lines 360-486): Intent classifier (`nxLlmClassify`) with entity allowlists, closed enums, and wildcard scope injection blocking.
- `nexus_llm.php` (lines 559-570): Student PII masking (`nxComposeCellSafe`) ensuring sensitive fields never leave the perimeter.

## Run it

```bash
php samples/04-nodus-parser/harness/test_parser.php

```

## Design decisions and trade-offs

- **Parser Only, Never Direct DB Executor**: The LLM translates text into a structured intent and entity payload. Deterministic downstream layers (planner, RBAC policy checks, and read-only queries) execute the data retrieval, preventing SQL injection or prompt-driven data destruction. The planner and RBAC matrix (nexus_semantic.php, chat.php) are NOT IN REPO - they were not extracted for this sample.
- **Post-Generation Anti-Hallucination Guard**: `nxLlmComposeGuard` validates that generated answers preserve all verified numbers, rejects invented causes (e.g. false technical failures), and blocks data denial if the underlying query returned rows.
- **Strict Entity Sanitization**: Entity keys are constrained to an allowlist, enums are strictly validated, dates cannot be future or older than 3 years, and scope escalations (e.g. `group: ALL`) are stripped.

## Limitations and what I would change

- **Downstream Semantic Planner**: The semantic planner (`nexus_semantic.php`) and institutional permission matrix (`chat.php`) reside in the mother repository. In this extract, the parser and composer are verified end-to-end with an automated harness test. SIMULATED: The test harness mocks the planner/RBAC steps since they are NOT IN REPO.
- **Local Fallback Model**: In high-latency or offline edge deployments, cloud LLM queries add latency. Running a quantized 3B parameter model on-premise would eliminate cloud provider dependencies.
- **Spanish Language in Prompts**: Nodus is a Spanish-language assistant. The system prompts, regex patterns, and reply templates in `nexus_llm.php` are in Spanish as functional product logic. This is documented in `tools/lang_allowlist.txt`.

## Related samples

- `01-rls-pgbouncer`: Multi-tenant session isolation in downstream query handlers.
- `02-audit-chain`: Tamper-evident logging of security queries and assistant actions.
