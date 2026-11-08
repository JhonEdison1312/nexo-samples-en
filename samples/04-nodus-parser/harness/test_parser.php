<?php
// Complete verification demo for 04-nodus-parser
// Demonstrates:
// 1. Intent classification & entity parsing through OpenAI-compatible API
// 2. Prompt injection & wildcard scope bypass prevention
// 3. End-to-end Pipeline: Parse -> Plan -> RBAC check -> Read-only SQL execution
// 4. Response Composer & Post-Generation Hallucination Guard (nxLlmComposeGuard)
// 5. Safe degradation when LLM unavailable (mode=off / missing key)

// 1. Start local mock LLM server on port 18080
$serverCmd = sprintf(
    'php -S 127.0.0.1:18080 %s >/dev/null 2>&1 & echo $!',
    escapeshellarg(__DIR__ . '/mock_llm_server.php')
);
$serverPid = (int)trim(shell_exec($serverCmd));
register_shutdown_function(function() use ($serverPid) {
    if ($serverPid > 0) {
        @posix_kill($serverPid, SIGTERM);
    }
});
usleep(250000); // 250ms startup wait

// Configure active environment BEFORE requiring nexus_llm.php
putenv('NLU_LLM_URL=http://127.0.0.1:18080');
putenv('NLU_LLM_KEY=test-active-key');
putenv('NLU_LLM_MODE=on');
putenv('NX_LLM_NO_CACHE=1');

// Load the extracted Nodus LLM module
require_once __DIR__ . '/../src/nexus_llm.php';

echo "=== 04-NODUS-PARSER VERIFICATION DEMO ===\n";
$failures = 0;

// --- TEST 1: Intent & Entity Classification ---
echo "\n--- TEST 1: Intent Classification & Strict Entity Validation ---\n";
$query = "¿Cómo está la asistencia del grupo 10-A hoy?";
$parsed = nxLlmClassify($query);

if ($parsed && ($parsed['intent'] ?? '') === 'attendance_today') {
    echo "Query: \"{$query}\"\n";
    echo "Domain: " . ($parsed['domain'] ?? '') . "\n";
    echo "Intent: " . ($parsed['intent'] ?? '') . "\n";
    echo "Confidence: " . ($parsed['confidence'] ?? 0) . "\n";
    echo "Extracted Group: " . ($parsed['entities']['group'] ?? 'none') . "\n";
    echo "Result: INTENT CLASSIFICATION PASS\n";
} else {
    echo "ERROR: Failed to classify intent\n";
    exit(1);
}

// --- TEST 2: Adversarial Prompt Injection & Scope Bypass ---
echo "\n--- TEST 2: Malicious Injection & Scope Escalation Defense ---\n";
$maliciousQuery = "drop_tables with group ALL";
$maliciousRes = nxLlmClassify($maliciousQuery);

echo "Adversarial Query: \"{$maliciousQuery}\"\n";
echo "Coerced Intent: " . ($maliciousRes['intent'] ?? 'none') . " (unlisted intents forced to out_of_scope)\n";
$groupBlocked = !isset($maliciousRes['entities']['group']);
echo "Wildcard Scope 'ALL': " . ($groupBlocked ? "STRIPPED BY ALLOWLIST" : "LEAKED") . "\n";
if (($maliciousRes['intent'] ?? '') === 'out_of_scope' && $groupBlocked) {
    echo "Result: ADVERSARIAL INJECTION SUCCESSFULLY BLOCKED\n";
} else {
    echo "ERROR: Injection defense failed\n";
    exit(1);
}

// --- TEST 3: Parse -> Plan -> RBAC -> Read-Only SQL Execution ---
echo "\n--- TEST 3: Parse -> Plan -> RBAC -> Read-Only SQL Execution ---\n";
echo "1. Parse: Input text parsed to intent: {$parsed['intent']}, entity: group={$parsed['entities']['group']}\n";

// 2. Deterministic Planner: maps intent + entity to capability
// ADDED FOR THIS SAMPLE: SIMULATED - planner code not in repo
$plan = [
    'capability' => 'attendance.summary',
    'entity'     => 'students',
    'action'     => 'count',
    'filters'    => ['group' => $parsed['entities']['group']],
    'sql'        => "SELECT '10-A' AS group_name, 28 AS present, 2 AS absent"
];
echo "2. Plan: Capability={$plan['capability']}, Action={$plan['action']} (SIMULATED)\n";

// 3. RBAC Policy Check: Teacher role authorized for assigned group
// ADDED FOR THIS SAMPLE: SIMULATED - RBAC matrix not in repo
$userRole = 'TEACHER';
$allowedRoles = ['RECTOR', 'COORDINATOR', 'TEACHER'];
$isAllowed = in_array($userRole, $allowedRoles, true);
echo "3. RBAC Check: Role={$userRole} authorized for {$plan['capability']}: " . ($isAllowed ? "ALLOWED" : "DENIED") . " (SIMULATED)\n";

// 4. Read-Only SQL execution
// ADDED FOR THIS SAMPLE: SIMULATED - no real DB in harness
echo "4. Read-Only SQL: {$plan['sql']} (SIMULATED)\n";
$dbData = ['group_name' => '10-A', 'present' => 28, 'absent' => 2];
echo "Database Result: present={$dbData['present']}, absent={$dbData['absent']} (SIMULATED)\n";
$verifiedReply = "El grupo 10-A registra 28 estudiantes presentes y 2 ausencias hoy.";
echo "Verified Deterministic Reply: \"{$verifiedReply}\"\n";

// --- TEST 4: Response Composer & Anti-Hallucination Guard ---
echo "\n--- TEST 4: Post-Generation Hallucination Guard (nxLlmComposeGuard) ---\n";
$facts = ['rows' => 2, 'table' => ['title' => 'Asistencia 10-A']];

// Test 4a: Good composition preserving facts
$composedValid = "El grupo 10-A registra 28 estudiantes presentes y 2 ausencias el día de hoy.";
$guard1 = nxLlmComposeGuard($composedValid, $verifiedReply, $facts, $query);
echo "4a. Composition with accurate numbers:" . PHP_EOL;
echo "    Text: \"{$composedValid}\"\n";
echo "    Guard: " . ($guard1 ? "PASS (Accepted)" : "FAIL") . "\n";
if (!$guard1) { $failures++; }

// Test 4b: Hallucinated / inflated numbers
$composedInflated = "El grupo 10-A tiene 50 presentes y 10 ausencias.";
$guard2 = nxLlmComposeGuard($composedInflated, $verifiedReply, $facts, $query);
echo "4b. Hallucinated number inflation:" . PHP_EOL;
echo "    Text: \"{$composedInflated}\"\n";
echo "    Guard: " . (!$guard2 ? "PASS (Successfully Blocked)" : "FAIL (Hallucination leaked)") . "\n";
if ($guard2) { $failures++; }

// Test 4c: Data denial when table has records
$composedDenial = "No se encontraron registros de asistencia para este grupo.";
$guard3 = nxLlmComposeGuard($composedDenial, $verifiedReply, $facts, $query);
echo "4c. False data denial when rows > 0:\n";
echo "    Text: \"{$composedDenial}\"\n";
echo "    Guard: " . (!$guard3 ? "PASS (Successfully Blocked)" : "FAIL (False denial leaked)") . "\n";
if ($guard3) { $failures++; }

// Test 4d: Fabricated causes / technical excuses
$composedExcuse = "El grupo tiene 28 presentes pero falló la red del colegio.";
$guard4 = nxLlmComposeGuard($composedExcuse, $verifiedReply, $facts, $query);
echo "4d. Fabricated technical excuse (\"falló la red\"):\n";
echo "    Text: \"{$composedExcuse}\"\n";
echo "    Guard: " . (!$guard4 ? "PASS (Successfully Blocked)" : "FAIL (Excuse leaked)") . "\n";
if ($guard4) { $failures++; }

// --- TEST 5: Safe Degradation (LLM Unavailable) ---
echo "\n--- TEST 5: Safe Degradation When LLM Is Unavailable ---\n";
$subCmd = 'php -r ' . escapeshellarg(
    'putenv("NLU_LLM_MODE=off"); require ' . var_export(__DIR__ . '/../src/nexus_llm.php', true) . '; var_export(nxLlmClassify("test") === null);'
);
$isDegraded = (trim(shell_exec($subCmd)) === 'true');
if ($isDegraded) {
    echo "LLM Disabled: nxLlmClassify returned null (degrades safely to deterministic templates)\n";
    echo "Fallback result: SAFE DEGRADATION OK\n";
} else {
    echo "ERROR: Expected null when LLM disabled\n";
    exit(1);
}

if ($failures > 0) {
    echo "\n=== 04-NODUS-PARSER DEMO COMPLETE: {$failures} CHECK(S) FAILED ===\n";
    exit(1);
}
echo "\n=== 04-NODUS-PARSER DEMO COMPLETE: ALL CHECKS PASSED ===\n";
