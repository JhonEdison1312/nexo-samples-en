// ============================================================
// Reliable Queue: LMOVE atomically moves ingest -> processing
// ============================================================

// Atomic Lua script that does LMOVE + injects timestamp.
// This guarantees that, if the worker dies, the GC can measure how long
// the item has been in processing and reinsert it.
$scriptReliablePop = <<<'LUA'
local ingest = KEYS[1]
local processing = KEYS[2]
local now = tonumber(ARGV[1])
local item = redis.call('LMOVE', ingest, processing, 'RIGHT', 'LEFT')
if item then
    local ok, job = pcall(cjson.decode, item)
    if ok and job then
        job.processing_since = now
        local newItem = cjson.encode(job)
        redis.call('LREM', processing, 0, item)
        redis.call('LPUSH', processing, newItem)
        return newItem
    end
    return item
end
return nil
LUA;

// Garbage Collector — reinserts zombie jobs into ingest
// (more than 5 minutes in processing without successful commit).
$scriptGc = <<<'LUA'
local processing = KEYS[1]
local ingest = KEYS[2]
local maxAge = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local items = redis.call('LRANGE', processing, 0, -1)
local recovered = 0
for i = 1, #items do
    local item = items[i]
    local ok, job = pcall(cjson.decode, item)
    if ok and job and job.processing_since then
        if (now - job.processing_since) > maxAge then
            redis.call('LREM', processing, 0, item)
            redis.call('LPUSH', ingest, item)
            recovered = recovered + 1
        end
    else
        redis.call('LREM', processing, 0, item)
        redis.call('LPUSH', ingest, item)
        recovered = recovered + 1
    end
end
return recovered
LUA;

$GC_MAX_AGE_SEC = (int)(getenv('BIOMETRIC_GC_MAX_AGE') ?: 300);
$EMPTY_QUEUE_SLEEP_US = (int)(getenv('BIOMETRIC_EMPTY_QUEUE_SLEEP_US') ?: 1_000_000); // 1s default (avoids 20 polls/s on Upstash)

logW('START', 'Biometric async worker started');
$redis = null;
try {
    $redis = getRedisConnection(true);
} catch (Exception $e) {}

$iterations = 0;
$lastGc = 0;
$lastHeartbeat = 0;
$lastOutboxDrain = 0;

// D-1: drains ingest_outbox — the API writes the durable job in the same tx as
// the event when Redis fails; here the full pipeline runs even if Redis
// remains down (direct PG). Claims with SKIP LOCKED, processes with processJob
// (which handles its own tx) and marks DONE; old PROCESSING returns to PENDING.
function drainOutbox(PDO $conn): int {
    $done = 0;
    try {
        $conn->exec("BEGIN");
        $conn->exec("SELECT set_config('app.current_role', 'SYSTEM_WORKER', true)");
        // Re-queue orphaned claims (>5 min in PROCESSING = worker died)
        $conn->exec("UPDATE ingest_outbox SET status='PENDING' WHERE status='PROCESSING' AND processed_at IS NULL AND created_at < NOW() - INTERVAL '5 minutes'");
        $rows = $conn->query(
            "SELECT outbox_id, payload FROM ingest_outbox
             WHERE status='PENDING' ORDER BY created_at
             FOR UPDATE SKIP LOCKED LIMIT 10"
        )->fetchAll(PDO::FETCH_ASSOC);
        $ids = array_map(fn($r) => $r['outbox_id'], $rows);
        if ($ids) {
            $in = implode(',', array_map(fn($id) => $conn->quote($id), $ids));
            $conn->exec("UPDATE ingest_outbox SET status='PROCESSING', attempts=attempts+1 WHERE outbox_id IN ($in)");
        }
        $conn->exec("COMMIT");
    } catch (Throwable $e) {
        try { $conn->exec("ROLLBACK"); } catch (Throwable $i) {}
        logW('OUTBOX_CLAIM_ERR', $e->getMessage());
        return 0;
    }
    foreach ($rows as $r) {
        $job = json_decode($r['payload'], true);
        $ok = false;
        if ($job) {
            try { $ok = processBiometricJob($job, $conn); }
            catch (Throwable $e) { logW('OUTBOX_JOB_ERR', $e->getMessage()); }
        }
        try {
            $conn->exec("BEGIN");
            $conn->exec("SELECT set_config('app.current_role', 'SYSTEM_WORKER', true)");
            if ($ok) {
                $conn->prepare("UPDATE ingest_outbox SET status='DONE', processed_at=NOW() WHERE outbox_id=?")
                     ->execute([$r['outbox_id']]);
            } else {
                // After 5 attempts goes to implicit DLQ (FAILED remains visible)
                $conn->prepare("UPDATE ingest_outbox SET status = CASE WHEN attempts >= 5 THEN 'FAILED' ELSE 'PENDING' END WHERE outbox_id=?")
                     ->execute([$r['outbox_id']]);
            }
            $conn->exec("COMMIT");
        } catch (Throwable $e) {
            try { $conn->exec("ROLLBACK"); } catch (Throwable $i) {}
        }
        if ($ok) $done++;
    }
    return $done;
}

// Execution guard: including the file (probes/tests) does not launch the daemon.
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) {
while (!$shutdown) {
    try {
        // D-1: drain the durable outbox every ~15s (or on each Redis idle)
        if (time() - $lastOutboxDrain >= 15) {
            $lastOutboxDrain = time();
            try { drainOutbox($pdo); } catch (Throwable $e) { logW('OUTBOX_DRAIN_ERR', $e->getMessage()); }
        }

        if (!$redis) {
            sleep(15);
            try { $redis = getRedisConnection(true); } catch (Exception $e) {}
            if (!$redis) continue;
        }

        // Heartbeat every 30 seconds
        if (time() - $lastHeartbeat >= 30) {
            $lastHeartbeat = time();
            try { sendHeartbeat($redis); } catch (Exception $e) {}
        }

        // Atomic Lua pop + timestamp injection.
        $item = false;
        try {
            $item = $redis->eval($scriptReliablePop, ['queue:biometric_ingest', 'queue:biometric_processing', time()], 2);
        } catch (Exception $e) {
            logW('REDIS_ERR', $e->getMessage());
            $redis = null; // Force reconnect on next iteration
            @touch('/tmp/redis_circuit_open'); // Trip circuit breaker manually
            continue;
        }
        if (!$item) { usleep($EMPTY_QUEUE_SLEEP_US); continue; }

        $job = json_decode($item, true);
        if (!$job) {
            try { $redis->lRem('queue:biometric_processing', $item, 0); } catch (Exception $e) {}
            continue;
        }

        try {
            $ok = processBiometricJob($job, $pdo);
            if ($ok) {
                // ONLY remove from processing AFTER successful commit()
                $redis->lRem('queue:biometric_processing', $item, 0);
                logW('OK', sprintf("action=%s req=%s", $job['action'] ?? '?', $job['request_id'] ?? 'n/a'));
            } else {
                // Logic failure: requeue on the main queue to retry (same as DB exception)
                $redis->lPush('queue:biometric_ingest', $item);
                $redis->lRem('queue:biometric_processing', $item, 0);
                logW('LOGIC_FAIL', sprintf("action=%s, requeued", $job['action'] ?? '?'));
            }
        } catch (Exception $e) {
            logW('ERR', $e->getMessage());
            $jobArray = json_decode($item, true) ?: [];
            $retries = ($jobArray['retries'] ?? 0) + 1;
            $jobArray['retries'] = $retries;

            if ($retries <= 3) {
                $redis->rPush('queue:biometric_ingest', json_encode($jobArray, JSON_UNESCAPED_UNICODE));
            } else {
                $redis->rPush('queue:biometric_dlq', json_encode($jobArray, JSON_UNESCAPED_UNICODE));
            }
            $redis->lRem('queue:biometric_processing', $item, 0);
            
            // Reconnect PDO if it failed (db.php recrea $pdo global)
            if (strpos($e->getMessage(), 'server closed the connection') !== false || strpos($e->getMessage(), 'gone away') !== false) {
                require __DIR__ . '/../core/db.php';
            }
        }
    } catch (Exception $e) {
        logW('FATAL', $e->getMessage());
        sleep(15);
        $redis = null; // Force reconnect
    }

    // Zombie GC every 60 seconds.
    if (time() - $lastGc >= 60) {
        $lastGc = time();
        try {
            $recovered = $redis->eval($scriptGc, ['queue:biometric_processing', 'queue:biometric_ingest', $GC_MAX_AGE_SEC, time()], 2);
            if ($recovered > 0) {
                logW('GC_ZOMBIE', "Recovered {$recovered} zombie job(s) after {$GC_MAX_AGE_SEC}s");
            }
        } catch (Exception $e) {
            logW('GC_ERR', $e->getMessage());
        }
    }

    if (++$iterations % 1000 === 0) {
        gc_collect_cycles();
        $mem = memory_get_peak_usage(true) / 1024 / 1024;
        if ($mem > 256) { logW('MEM', "{$mem}MB > 256MB restart"); exit(0); }
    }
}
logW('STOP', 'Biometric worker shutdown'); exit(0);
}


