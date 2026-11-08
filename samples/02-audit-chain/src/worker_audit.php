/**
 * Calculates HMAC-SHA256 linking a log with the previous record in the chain.
 *
 * @param string|null $prevHash Hash of previous record.
 * @param string|null $schoolId UUID of school.
 * @param string|null $actorId UUID of actor.
 * @param string $eventType Event type.
 * @param string $description Description.
 * @param string $ipAddress IP address.
 * @param string $createdAt Timestamp.
 * @param string $secret HMAC secret.
 * @return string HMAC-SHA256 hash.
 */
function calculateAuditHash($prevHash, $schoolId, $actorId, $eventType, $description, $ipAddress, $createdAt, $secret) {
    $prevHash = $prevHash ?: 'GENESIS';
    $schoolId = $schoolId ?: 'NULL';
    $actorId = $actorId ?: 'NULL';
    $payload = "{$prevHash}|{$schoolId}|{$actorId}|{$eventType}|{$description}|{$ipAddress}|{$createdAt}";
    return hash_hmac('sha256', $payload, $secret);
}

/**
 * Inserts a batch of audit logs in a transaction maintaining the hash chain.
 *
 * @param PDO $conn PDO connection.
 * @param array $rows Rows decoded from Redis.
 * @return void
 *
 * Side effects: starts and commits/rolls back a transaction; on error
 * re-enqueues failed rows to `queue:audit_logs`.
 */
function insertBatch($conn, array $rows) {
    if (empty($rows)) return;
    
    $secret = getenv('APP_NEXO_HMAC_SECRET');
    if (!$secret || $secret === 'default-secret-change-me') {
        error_log('[AUDIT_WORKER] FATAL: APP_NEXO_HMAC_SECRET is not configured or is the default. Worker cannot start.');
        exit(1);
    }
    $lastHashes = []; // In-memory cache for the batch

    $conn->beginTransaction();
    // The chain trigger requires the GUC inside the tx (Supavisor
    // transaction mode discards session-level ones).
    if (function_exists('nxDbSetHmac')) nxDbSetHmac($conn);
    try {
        $stmt = $conn->prepare("
            INSERT INTO global_audit_logs
                (log_id, school_id, performed_by_user_id, action_type,
                 description, ip_address, action_details, created_at,
                 prev_audit_id, chain_hash)
            VALUES
                (?, ?, ?, ?, ?,
                 ?::inet,
                 ?::jsonb,
                 ?, ?, ?)
        ");
        
        foreach ($rows as $row) {
            $schoolId = $row['school_id'];

            // RLS: gal_insert/gal_select require school_id = context — set it
            // by school within the tx (set_config true ≡ SET LOCAL).
            // The role allows inserting system events without school
            // (pre-auth: LOGIN_*, etc.); school_id delimits what is readable.
            if (!($ctxSet ?? false)) {
                $conn->exec("SELECT set_config('app.current_role', 'SYSTEM_WORKER', true)");
                $ctxSet = true;
            }
            if (($lastCtx ?? null) !== $schoolId) {
                if ($schoolId === null) {
                    $conn->exec("SELECT set_config('app.current_school_id', '', true)");
                } else {
                    $conn->exec("SELECT set_config('app.current_school_id', " . $conn->quote((string)$schoolId) . ", true)");
                }
                $lastCtx = $schoolId;
            }

            if (!isset($lastHashes[$schoolId])) {
                $chk = $conn->prepare("SELECT log_id, chain_hash FROM global_audit_logs WHERE school_id = ? ORDER BY created_at DESC, log_id DESC LIMIT 1");
                $chk->execute([$schoolId]);
                $lastHashes[$schoolId] = $chk->fetch(PDO::FETCH_ASSOC) ?: ['log_id' => null, 'chain_hash' => 'GENESIS'];
            }
            
            $prevAuditId = $lastHashes[$schoolId]['log_id'];
            $prevHash = $lastHashes[$schoolId]['chain_hash'];
            
            $logId = generateUuidV4();
            $actorId = $row['actor_id'];
            $eventType = $row['event_type'];
            $description = $row['description'];
            $ipAddress = $row['ip_address'] ?? '0.0.0.0';
            
            // Format to match PostgreSQL jsonb::text cast style
            $uriStr = isset($row['uri']) ? '"' . str_replace('"', '\"', $row['uri']) . '"' : '"N/A"';
            $reqStr = isset($row['request_id']) ? '"' . str_replace('"', '\"', $row['request_id']) . '"' : 'null';
            $actionDetailsJson = '{"uri": ' . $uriStr . ', "request_id": ' . $reqStr . '}';
            
            // Format to match PostgreSQL timestamptz cast style (YYYY-MM-DD HH:MM:SS+00)
            $createdAt = $row['created_at'] ?? gmdate('Y-m-d H:i:s');
            $createdAtPg = date('Y-m-d H:i:s+00', strtotime($createdAt));

            $hash = calculateAuditHash($prevHash, $schoolId, $actorId, $eventType, $actionDetailsJson, $ipAddress, $createdAtPg, $secret);

            $stmt->execute([
                $logId,
                $schoolId,
                $actorId,
                $eventType,
                $description,
                $ipAddress,
                $actionDetailsJson,
                $createdAt,
                $prevAuditId,
                $hash
            ]);
            
            // Update the batch cache for the next record
            $lastHashes[$schoolId] = ['log_id' => $logId, 'chain_hash' => $hash];
        }
