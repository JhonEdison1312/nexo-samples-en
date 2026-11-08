#!/bin/bash
# ADDED FOR THIS SAMPLE
# test_reliable_queue.sh — Shell wrapper running the Python queue harness.
# Starts Redis (if not running) and invokes test_queue.py.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/../../.."

REDIS_PORT="${REDIS_PORT:-16379}"

if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    echo "Starting Redis via tools/env/up.sh..."
    bash "${REPO_ROOT}/tools/env/up.sh"
fi

echo "Running biometric reliable queue invariant tests..."
python3 "${SCRIPT_DIR}/test_queue.py"
