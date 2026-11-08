# =============================================================================
# NEXO Samples - Makefile
# =============================================================================
# ADDED FOR THIS SAMPLE
# =============================================================================

.PHONY: up down verify verify-fast help extract deps-check test-01 test-02 test-03 test-04 test-05 test-06 verify-provenance

ORIGIN ?=

help:
	@echo "NEXO Samples - Commands:"
	@echo "  make deps-check                    - Check and print missing dependencies"
	@echo "  make up                            - Start user-space env (PostgreSQL, PgBouncer, Redis)"
	@echo "  make down                          - Stop user-space env"
	@echo "  make extract ORIGIN=<path>         - Extract code from mother repo (WRITES samples)"
	@echo "  make verify-provenance ORIGIN=<path> - Verify provenance only (READ-ONLY)"
	@echo "  make verify ORIGIN=<path>          - Run master verification (G1-G7)"
	@echo "  make verify-fast                   - Quick syntax and docs check"
	@echo "  make test-01                       - Run sample 01 tests"
	@echo "  make test-02                       - Run sample 02 tests"
	@echo "  make test-03                       - Run sample 03 tests"
	@echo "  make test-04                       - Run sample 04 tests"
	@echo "  make test-05                       - Run sample 05 tests"
	@echo "  make test-06                       - Run sample 06 tests"
	@echo "  make help                          - Show this help"

deps-check:
	@echo "=== Checking Dependencies ==="
	@missing=0; \
	check() { if command -v "$$1" >/dev/null 2>&1; then echo "OK: $$1"; else echo "MISSING: $$1 ($$2)"; missing=$$((missing+1)); fi; }; \
	opt() { if command -v "$$1" >/dev/null 2>&1; then echo "OK: $$1"; else echo "OPTIONAL (docker route / local gates only): $$1 ($$2)"; fi; }; \
	opt docker "apt: docker.io or docker-ce"; \
	opt docker-compose "apt: docker-compose"; \
	check python3 "apt: python3, version 3.11+"; \
	check php "apt: php8.2 or php, version 8.2+"; \
	check psql "apt: postgresql-client, version 15+"; \
	check pgbouncer "apt: pgbouncer"; \
	check redis-server "apt: redis-server"; \
	check g++ "apt: g++, with C++20 support"; \
	check cmake "apt: cmake"; \
	check shellcheck "apt: shellcheck"; \
	opt gitleaks "https://github.com/gitleaks/gitleaks"; \
	opt actionlint "https://github.com/rhysd/actionlint"; \
	check sqlite3 "apt: sqlite3"; \
	if php -m 2>/dev/null | grep -q mbstring; then echo "OK: php-mbstring"; else echo "MISSING: php-mbstring (apt: php-mbstring)"; missing=$$((missing+1)); fi; \
	if php -m 2>/dev/null | grep -q curl; then echo "OK: php-curl"; else echo "MISSING: php-curl (apt: php-curl)"; missing=$$((missing+1)); fi; \
	if php -m 2>/dev/null | grep -q pdo_pgsql; then echo "OK: php-pgsql"; else echo "OPTIONAL (not needed by tests): php-pgsql (apt: php-pgsql)"; fi; \
	if php -m 2>/dev/null | grep -q redis; then echo "OK: php-redis"; else echo "OPTIONAL (not needed by tests): php-redis (apt: php-redis)"; fi; \
	if php -m 2>/dev/null | grep -q sqlite3; then echo "OK: php-sqlite3"; else echo "OPTIONAL (not needed by tests): php-sqlite3 (apt: php-sqlite3)"; fi; \
	if python3 -c "import redis" 2>/dev/null; then echo "OK: python3-redis"; else echo "MISSING: python3-redis (pip: redis)"; missing=$$((missing+1)); fi; \
	echo "=== End of dependency check (missing=$$missing) ==="; \
	[ $$missing -eq 0 ]

up:
	@tools/env/up.sh

down:
	@tools/env/down.sh

extract:
	@echo "Extracting code from ORIGIN=$(ORIGIN)..."
	@python3 tools/provenance/extract.py "$(ORIGIN)"
	@echo "Extraction complete. Run 'make verify-provenance ORIGIN=$(ORIGIN)' to verify."

verify-provenance:
	@test -n "$(ORIGIN)" || (echo "ERROR: ORIGIN must be set for verify-provenance" && exit 1)
	@python3 tools/provenance/verify.py "$(ORIGIN)"

verify:
	@python3 tools/run_verify.py $(ORIGIN)

verify-structure:
	@python3 tools/verify_structure.py

verify-structure-selftest:
	@python3 tools/verify_structure.py --self-test

verify-fast:
	@echo "=== FAST VERIFICATION ==="
	@find samples -name "*.php" -exec php -l {} +
	@python3 tools/docs_lint.py
	@files=$$(find samples tools -name '*.sh' 2>/dev/null); [ -z "$$files" ] || shellcheck -S error $$files

test-01:
	@cd samples/01-rls-pgbouncer/harness && bash test_pgbouncer_leak.sh

test-02:
	@cd samples/02-audit-chain/harness && bash test_tampering.sh

test-03:
	@cd samples/03-edge-pipeline/harness && bash test_edge_pipeline.sh

test-04:
	@php samples/04-nodus-parser/harness/test_parser.php

test-05:
	@python3 samples/05-redis-reliable-queue/harness/test_queue.py

test-06:
	@bash samples/06-table-partitioning/harness/test_partitioning.sh
