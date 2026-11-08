#!/usr/bin/env bash
# ADDED FOR THIS SAMPLE
# Test offline edge pipeline:
# 1. Device-bound key provisioning post-fix (fail-closed without opt-in, allowed with NEXO_ALLOW_DEV_KEY_FALLBACK=1)
# 2. SQLite local outbox initialization with WAL mode
# 3. Offline biometric attendance capture
# 4. Network failure handling and retry count increment
# 5. Encrypted AES-256-GCM upload with server deduplication via Redis NX
# 6. Replay attack rejection
# The binary asserts every step and exits non-zero on any mismatch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN="${SCRIPT_DIR}/edge_demo"

SOURCES=(
  "${SAMPLE_DIR}/src/encryption.cpp"
  "${SAMPLE_DIR}/src/sqlite_manager.cpp"
  "${SAMPLE_DIR}/src/DevStubBiometricSensor.cpp"
  "${SAMPLE_DIR}/src/cloud_manager.cpp"
  "${SAMPLE_DIR}/src/utils/ConfigManager.cpp"
  "${SCRIPT_DIR}/main_demo.cpp"
)

needs_build=0
if [[ ! -x "${BIN}" ]]; then
    needs_build=1
else
    for src in "${SOURCES[@]}"; do
        if [[ "${src}" -nt "${BIN}" ]]; then
            needs_build=1
            break
        fi
    done
fi

if [[ "${needs_build}" -eq 1 ]]; then
    echo "Compiling edge_demo..."
    if ! g++ -std=c++20 -Wall -Wextra -Wpedantic \
      -I "${SAMPLE_DIR}/src/include" \
      -I "${SAMPLE_DIR}/src" \
      -I "${SAMPLE_DIR}/harness/include" \
      "${SAMPLE_DIR}/src/encryption.cpp" \
      "${SAMPLE_DIR}/src/sqlite_manager.cpp" \
      "${SAMPLE_DIR}/src/DevStubBiometricSensor.cpp" \
      "${SAMPLE_DIR}/src/cloud_manager.cpp" \
      "${SAMPLE_DIR}/src/utils/ConfigManager.cpp" \
      "${SCRIPT_DIR}/main_demo.cpp" \
      -lsqlite3 -lcrypto -lssl -lcurl -lspdlog -lfmt \
      -o "${BIN}" 2> "${SCRIPT_DIR}/.build.log"; then
        cat "${SCRIPT_DIR}/.build.log" >&2
        exit 1
    fi
fi

# Run the compiled binary (exits non-zero on any failed assertion)
"${BIN}"
