# Security Policy

## Demo-Only Credentials

This repository contains sample code for demonstration purposes. The credentials in harness configurations are for local testing only and are NOT deployment credentials.

### Harness Demo Credentials

- **PostgreSQL (samples 01, 02)**: User `nexo_app` with password `demo_password` (localhost only)
- **Redis (sample 05)**: No authentication configured (localhost only)
- **Cloud API (sample 03)**: Mock server on localhost:8080, no real network calls

## Security by Design in Extracts

The demonstrated security patterns include:

1. **PostgreSQL Row-Level Security (RLS)**: Multi-tenant isolation with `SET LOCAL` to prevent cross-tenant context leaks
2. **AES-256-GCM Encryption**: 256-bit keys with 12-byte random IV and 16-byte authentication tag
3. **HMAC Audit Chain**: Tamper-evident logging with hash-chained HMAC-SHA256
4. **Anti-Replay Nonces**: Unique payload nonces verified via Redis `SET key 1 NX EX 604800`
5. **Fail-Closed Hardware Binding**: Hardware-bound keys with explicit opt-in for dev fallback
6. **LLM Guardrails**: Parser only classifies, deterministic layers execute, system degrades without model

## Reporting Security Issues

For the NEXO prototype (private repository), report security issues through appropriate channels. This public samples repository contains only sanitized extracts and no deployment secrets.

## Disclaimer

This is a portfolio repository demonstrating architectural patterns from a prototype. The code is NOT deployment-ready and should not be deployed as-is in any environment.
