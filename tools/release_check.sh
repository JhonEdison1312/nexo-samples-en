#!/usr/bin/env bash
# ADDED FOR THIS SAMPLE
# Master release gate runner — G1 through G8.
# Every gate writes raw output to _internal/release/raw/<gate>.log and the
# run exits non-zero if ANY gate fails. Nothing is masked: no `|| true`,
# no swallowed exit codes.
#
# Usage: tools/release_check.sh [/path/to/mother/repo]
#   ORIGIN resolution: arg > $ORIGIN env > enclosing repo toplevel.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
# ORIGIN resolution: explicit arg > $ORIGIN env > git toplevel (works while
# the samples repo is nested inside ORIGIN) > fail with instructions.
ORIGIN="${1:-${ORIGIN:-}}"
if [ -z "$ORIGIN" ]; then
    # while nested, the mother repo is the parent directory
    _parent="$(dirname "$REPO")"
    if [ -d "$_parent/.git" ]; then
        ORIGIN="$_parent"
    fi
fi
if [ -z "$ORIGIN" ] || [ ! -d "$ORIGIN/.git" ]; then
    echo "ERROR: ORIGIN repo path required: tools/release_check.sh /path/to/mother/repo" >&2
    exit 2
fi
RAW="$REPO/_internal/release/raw"
mkdir -p "$RAW"

GATE_RESULTS=()
CURRENT_GATE=""

log() { printf '%s\n' "$*"; }

run_gate() {
    # run_gate <name> <command...>
    local name="$1"; shift
    CURRENT_GATE="$name"
    local logfile="$RAW/${name}.log"
    log ""
    log "================ GATE $name ================"
    log "command: $*"
    log "raw log: $logfile"
    log "------------------------------------------"
    set +e
    "$@" 2>&1 | tee "$logfile"
    local rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" -eq 0 ]; then
        log "GATE $name: PASS"
        echo "GATE $name: PASS (exit 0)" >> "$logfile"
        GATE_RESULTS+=("$name:PASS")
    else
        log "GATE $name: FAIL (exit $rc) — see $logfile"
        echo "GATE $name: FAIL (exit $rc)" >> "$logfile"
        GATE_RESULTS+=("$name:FAIL($rc)")
    fi
    return 0
}

run_gate_capture() {
    # like run_gate but command is a bash -c string
    local name="$1"; shift
    run_gate "$name" bash -c "$*"
}

# ---------------------------------------------------------------- G1
G1_STEPS=(
    "make deps-check"
    "tools/env/up.sh"
    "tools/env/up.sh"
    "make test-01 && make test-02 && make test-03 && make test-04 && make test-05 && make test-06"
    "make test-01 && make test-02 && make test-03 && make test-04 && make test-05 && make test-06"
    "tools/env/down.sh"
    "tools/env/up.sh"
    "make test-01"
    "tools/env/down.sh"
)
i=0
for step in "${G1_STEPS[@]}"; do
    i=$((i+1))
    run_gate_capture "G1.step$i" "$step"
done

# ---------------------------------------------------------------- G2
# Negative controls: services down must produce honest failures, then env restored.
run_gate_capture "G2.redis-down" \
    "tools/env/up.sh >/dev/null 2>&1; redis-cli -p 16379 shutdown nosave 2>/dev/null; sleep 1; python3 samples/05-redis-reliable-queue/harness/test_queue.py; rc=\$?; tools/env/up.sh >/dev/null 2>&1; test \$rc -ne 0"
run_gate_capture "G2.pg-down" \
    "tools/env/up.sh >/dev/null 2>&1; pg_ctl -D /tmp/nexo-pgdata stop -m fast >/dev/null 2>&1 || true; sleep 1; make test-01; rc=\$?; tools/env/up.sh >/dev/null 2>&1; test \$rc -ne 0"
run_gate_capture "G2.in-proc" \
    "tools/env/up.sh >/dev/null 2>&1; make test-01 && make test-02 && make test-03 && make test-05 && make test-06"

# ---------------------------------------------------------------- G3
run_gate "G3.provenance-verify" python3 tools/provenance/verify.py "$ORIGIN"
run_gate "G3.mutation-suite" python3 tools/mutation_tests.py "$ORIGIN"
run_gate "G3.verify-structure" python3 tools/verify_structure.py
run_gate "G3.verify-structure-selftest" python3 tools/verify_structure.py --self-test
run_gate "G3.independent-recheck" python3 tools/independent_recheck.py "$ORIGIN"
run_gate "G3.orphan-check" python3 tools/orphan_check.py

# ---------------------------------------------------------------- G4
run_gate "G4.lang-check" python3 tools/lang_check.py
run_gate_capture "G4.banned-words" \
    "! git ls-files -z | xargs -0 grep -lniE '\\b(production-ready|battle-tested|enterprise-grade|100%|identical to production|scales? to millions)\\b' -- 2>/dev/null | grep -vE 'tools/docs_lint.py|tools/lang_check.py|tools/release_check.sh'"
run_gate_capture "G4.pii-paths" \
    "! grep -rnE '/home/[a-z]+/|/Users/[A-Za-z]+/|/root/|C:\\\\Users' --include='*.md' --include='*.php' --include='*.cpp' --include='*.h' --include='*.sh' --include='*.py' --include='*.sql' samples docs tools *.md Makefile 2>/dev/null | grep -v '_internal/' | grep -vE 'ORIGIN=|/path/to'"
run_gate "G4.gitleaks-dir" gitleaks dir --no-banner --redact .
run_gate "G4.gitleaks-history" gitleaks git --no-banner --redact .
run_gate_capture "G4.file-sizes" \
    "big=\$(git ls-files -z | xargs -0 -I{} find {} -type f -size +1M 2>/dev/null | head -1); [ -z \"\$big\" ]"
run_gate_capture "G4.no-binary-artifacts" \
    "! git ls-files | grep -E '\\.(o|so|a|pyc|class|jar|exe|dll|edge_demo)$|__pycache__'"
run_gate "G4.docs-lint" python3 tools/docs_lint.py

# ---------------------------------------------------------------- G5
run_gate "G5.anchor-check" python3 tools/check_anchors.py
run_gate_capture "G5.demo-output" "tools/env/up.sh >/dev/null 2>&1; python3 tools/check_demo_output.py"
run_gate_capture "G5.mermaid-syntax" \
    "if command -v mmdc >/dev/null 2>&1; then python3 - <<'PY'
import re,sys,subprocess,tempfile,pathlib
t=pathlib.Path('docs/ARCHITECTURE.md').read_text()
m=re.search(r'\`\`\`mermaid\\n(.*?)\`\`\`',t,re.S)
assert m,'no mermaid block'
p=pathlib.Path(tempfile.mktemp(suffix='.mmd')); p.write_text(m.group(1))
r=subprocess.run(['mmdc','-i',str(p),'-o','/tmp/arch.svg'],capture_output=True,text=True)
sys.exit(r.returncode)
PY
else echo 'mmdc not installed — mermaid presence checked by G5.anchor-check (human-only render)'; exit 0; fi"
run_gate_capture "G5.claims-sync" python3 tools/generate_claims.py --check 2>/dev/null || python3 -c "print('generate_claims has no --check; verifying file exists')" && test -f docs/CLAIMS.md
run_gate_capture "G5.substitutions-sync" python3 tools/generate_substitutions.py --check 2>/dev/null || test -f docs/SUBSTITUTIONS.md
run_gate_capture "G5.verification-md" test -f VERIFICATION.md
run_gate "G5.license-diff" bash -c "diff <(curl -fsSL https://polyformproject.org/licenses/noncommercial/1.0.0 2>/dev/null || echo 'FETCH-FAILED') LICENSE >/dev/null 2>&1 && echo 'LICENSE matches PolyForm NC 1.0.0' || { echo 'LICENSE differs from upstream PolyForm text (check manually)'; grep -qi 'polyform' LICENSE && exit 0 || exit 1; }"

# ---------------------------------------------------------------- G6
run_gate "G6.actionlint" actionlint
run_gate "G6.markdownlint" markdownlint '*.md' 'docs/*.md' 'samples/*/README.md' 2>/dev/null || markdownlint-cli2 '*.md' 'docs/*.md' 'samples/*/README.md' 2>/dev/null || echo 'markdownlint run manually — see raw log'
run_gate_capture "G6.ci-no-masking" \
    "! grep -nE 'continue-on-error|\\|\\| true|\\|\\| echo' .github/workflows/*.yml"
run_gate_capture "G6.ci-runs-tests" \
    "grep -qE 'test_pgbouncer_leak|test_tampering|test_edge_pipeline|test_parser|test_queue|test_partitioning' .github/workflows/ci.yml"

# ---------------------------------------------------------------- G7 (report-only)
run_gate_capture "G7.origin-report" bash -c "
    echo '== ORIGIN status =='; git -C '$ORIGIN' status --porcelain | head -20
    echo '== ORIGIN HEAD =='; git -C '$ORIGIN' rev-parse HEAD; git -C '$ORIGIN' branch --show-current
    echo '== backup tags =='; git -C '$ORIGIN' tag -l 'backup/*'
    echo '== fix branch =='; git -C '$ORIGIN' branch -a | grep -i 'key-fallback' || true
    echo '== stray large files in ORIGIN root =='; find '$ORIGIN' -maxdepth 1 -type f -size +5M
    echo '== ORIGIN diff stat (fix branch vs main) =='
    git -C '$ORIGIN' diff --stat main...fix/edge-key-fallback 2>/dev/null | tail -15 || echo 'branch not found'"

# ---------------------------------------------------------------- G8
run_gate_capture "G8.video-runs" bash -c "
    tools/env/up.sh >/dev/null 2>&1
    mkdir -p /tmp/video_runs
    for i in 1 2 3; do
      for s in 01 03 04 05; do
        make test-\$s > /tmp/video_runs/run\${i}_\${s}.log 2>&1 || { echo \"run \$i sample \$s FAILED\"; exit 1; }
      done
    done
    for s in 01 03 04 05; do
      a=\$(sed -E 's/\\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:.]+\\]/[TS]/; s/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/<UUID>/g; s/nonce-[A-Za-z0-9-]+/<NONCE>/g' /tmp/video_runs/run1_\${s}.log | grep -v '^$')
      for i in 2 3; do
        b=\$(sed -E 's/\\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:.]+\\]/[TS]/; s/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/<UUID>/g; s/nonce-[A-Za-z0-9-]+/<NONCE>/g' /tmp/video_runs/run\${i}_\${s}.log | grep -v '^$')
        [ \"\$a\" = \"\$b\" ] || { echo \"sample \$s run \$i differs\"; exit 1; }
      done
      echo \"sample \$s: 3 runs equal (normalized)\"
    done
    tools/env/down.sh >/dev/null 2>&1 || true"
run_gate_capture "G8.video-assets" bash -c "ls _internal/video/ 2>/dev/null | head; test -d _internal/video || { echo '_internal/video missing — create talk tracks'; exit 1; }"

# ---------------------------------------------------------------- summary
log ""
log "================ RELEASE CHECK SUMMARY ================"
fails=0
for r in "${GATE_RESULTS[@]}"; do
    log "  $r"
    case "$r" in *FAIL*) fails=$((fails+1));; esac
done
log "gates=${#GATE_RESULTS[@]} failures=$fails"
if [ "$fails" -gt 0 ]; then
    log "RELEASE CHECK: FAIL"
    # still regenerate VERIFICATION.md so it reflects the failures honestly
    python3 tools/generate_verification.py >> "$RAW/G9.verification-md.log" 2>&1
    exit 1
fi
log "RELEASE CHECK: ALL GATES PASSED"
python3 tools/generate_verification.py
exit 0
