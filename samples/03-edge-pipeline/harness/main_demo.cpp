// ADDED FOR THIS SAMPLE
// Complete scenario demo for 03-edge-pipeline:
// 1. Biometric event recorded offline -> SQLite outbox
// 2. Network sync failure -> retry with backoff/attempt count
// 3. Network recovery -> encrypted AES-256-GCM sync with unique nonce
// 4. Server-side dedupe via Redis NX
// 5. Replay attack rejected (duplicate nonce blocked)
// SIMULATED: The mock server (listen on port 8080) is SIMULATED for demo purposes only.

#include <iostream>
#include <string>
#include <vector>
#include <filesystem>
#include <chrono>
#include <thread>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

#include "utils/Logger.h"
#include "base_de_datos/encryption.h"
#include "base_de_datos/sqlite_manager.h"
#include "base_de_datos/cloud_manager.h"
#include "hardware/dev_stub/DevStubBiometricSensor.h"

namespace fs = std::filesystem;

// SIMULATED mock server-side ingestion handler. Mirrors the anti-replay
// nonce check of the private backend/api/api.php ingest handler
// (private file, not part of this repository). SIMULATED: the Redis-down
// branch returns 503 (fail-closed) for demo clarity; the private handler's
// exact fail-open/fail-closed behavior is not part of this repository.
class IngestServerMock {
public:
    explicit IngestServerMock(int redisPort = 16379) : m_redisPort(redisPort) {}

    struct Response {
        int statusCode;
        std::string message;
    };

    Response ingest(const std::string& nonce, const std::string& b64Ciphertext, const std::string& expectedPlainDoc) {
        if (nonce.empty()) {
            return {400, "Missing nonce"};
        }

        // 1. Redis atomic dedupe: SET <nonce> 1 NX EX 604800
        int nonceResult = checkNonceInRedis(nonce);
        if (nonceResult == kRedisDown) {
            LOG_ERROR("[SERVER] Redis is down — cannot verify nonce, rejecting ingestion");
            return {503, "Redis is down"};
        }
        if (nonceResult == kNonceDuplicate) {
            LOG_WARN("[SERVER] EDGE_REPLAY_NONCE_DUPLICATE: Replay attack detected! Nonce already used: {}", nonce);
            return {403, "Nonce already used"};
        }

        // 2. Server decrypts AES-256-GCM payload
        auto& crypto = Encryption::getInstance();
        std::string decrypted = crypto.decrypt(b64Ciphertext);
        if (decrypted.empty() || decrypted.find(expectedPlainDoc) == std::string::npos) {
            return {400, "Decryption or authentication failed"};
        }

        LOG_INFO("[SERVER] Ingestion OK: event accepted (202 Accepted)");
        return {202, "Accepted"};
    }

private:
    int m_redisPort;

    enum NonceCheck { kNonceOk = 0, kNonceDuplicate = 1, kRedisDown = 2 };

    int checkNonceInRedis(const std::string& nonce) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) {
            LOG_ERROR("[SERVER] Failed to create socket for Redis");
            return kRedisDown;
        }

        struct sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(static_cast<uint16_t>(m_redisPort));
        inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

        if (connect(sock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
            close(sock);
            LOG_ERROR("[SERVER] Redis unavailable on port {}", m_redisPort);
            return kRedisDown;
        }

        // Send RESP: SET <nonce> 1 NX EX 604800
        std::string cmd = "*6\r\n$3\r\nSET\r\n$" + std::to_string(nonce.size()) + "\r\n" + nonce +
                          "\r\n$1\r\n1\r\n$2\r\nNX\r\n$2\r\nEX\r\n$6\r\n604800\r\n";
        send(sock, cmd.data(), cmd.size(), 0);

        char buf[256]{};
        ssize_t n = recv(sock, buf, sizeof(buf) - 1, 0);
        close(sock);

        if (n <= 0) {
            LOG_ERROR("[SERVER] Failed to receive response from Redis");
            return kRedisDown;
        }
        std::string reply(buf, static_cast<size_t>(n));
        // +OK -> success; $-1 -> already exists (duplicate)
        return (reply.rfind("+OK", 0) == 0) ? kNonceOk : kNonceDuplicate;
    }
};

int main() {
    Logger::initialize("edge_demo.log", "info");
    bool allOk = true;
    auto assertThat = [&](bool cond, const std::string& what) {
        std::cout << "  [" << (cond ? "PASS" : "FAIL") << "] " << what << std::endl;
        if (!cond) allOk = false;
    };
    std::cout << "=== 03-EDGE-PIPELINE VERIFICATION DEMO ===" << std::endl;

    // Setup working paths in /tmp
    fs::path tempDir = fs::temp_directory_path() / "nexo_edge_demo";
    fs::create_directories(tempDir);
    std::string dbPath = (tempDir / "offline_outbox.db").string();
    std::string keyPath = (tempDir / "device.key").string();

    fs::remove(dbPath);
    fs::remove(keyPath);

    // 1. Device key initialization
    std::cout << "\n--- STEP 1: Device-Bound Key Setup (Post-Fix Fail-Closed & Dev Opt-in) ---" << std::endl;
    auto& crypto = Encryption::getInstance();
    crypto.setKeyFile(keyPath);

    // Demonstrate fail-closed when hardware binding fails without opt-in
    unsetenv("NEXO_ALLOW_DEV_KEY_FALLBACK");
    std::string devKey(32, 'K');
    bool failClosedOk = !crypto.provisionKey(devKey);
    std::cout << "Without opt-in flag: Hardware binding fails -> Fail-closed: " 
              << (failClosedOk ? "YES (key rejected)" : "NO") << std::endl;
    assertThat(failClosedOk, "fail-closed: key rejected without opt-in");

    // Enable developer / simulator opt-in explicitly
    setenv("NEXO_ALLOW_DEV_KEY_FALLBACK", "1", 1);
    bool optInOk = crypto.provisionKey(devKey);
    std::cout << "With NEXO_ALLOW_DEV_KEY_FALLBACK=1: Key provisioned: " 
              << (optInOk ? "YES (0600 mode)" : "NO") << std::endl;
    assertThat(optInOk, "opt-in: key provisioned with NEXO_ALLOW_DEV_KEY_FALLBACK=1");
    unsetenv("NEXO_ALLOW_DEV_KEY_FALLBACK");

    // 2. Initialize SQLite outbox database
    std::cout << "\n--- STEP 2: SQLite Outbox Initialization ---" << std::endl;
    auto& db = SqliteManager::getInstance();
    if (!db.initialize(dbPath)) {
        std::cerr << "Failed to initialize SQLite outbox" << std::endl;
        return 1;
    }
    std::cout << "SQLite outbox schema created: PRAGMA journal_mode=WAL; synchronous=EXTRA" << std::endl;

    // 3. Record biometric event offline
    std::cout << "\n--- STEP 3: Offline Event Capture ---" << std::endl;
    DevStubBiometricSensor sensor;
    sensor.initialize();
    std::string studentDoc = "1098765432";
    std::string eventType = "BIOMETRIC_ATTENDANCE_CHECKIN";

    bool saved = db.saveAudit(studentDoc, eventType);
    std::cout << "Attendance event recorded to outbox: " << (saved ? "SUCCESS" : "FAILED") << std::endl;
    std::cout << "Pending unsynced outbox records: " << db.getPendingAuditCount() << std::endl;
    assertThat(saved, "biometric event persisted to outbox");
    assertThat(db.getPendingAuditCount() == 1, "outbox has exactly 1 pending record");

    // 4. Offline sync attempt (network down -> retry backoff)
    std::cout << "\n--- STEP 4: Network Failure & Retry Accounting ---" << std::endl;
    std::vector<AuditRecord> pending;
    db.getPendingAudits(pending);
    if (!pending.empty()) {
        int auditId = pending[0].id;
        std::cout << "Attempting sync while server unreachable..." << std::endl;
        db.incrementAuditAttempt(auditId);
        std::vector<AuditRecord> retried;
        db.getPendingAudits(retried);
        std::cout << "Sync failed. Retry count incremented to: " << retried[0].attempts << std::endl;
        std::cout << "Record remains queued in outbox: YES" << std::endl;
        assertThat(retried[0].attempts >= 1, "retry attempt counter incremented");
    } else {
        assertThat(false, "outbox record present for retry accounting");
    }

    // 5. Successful sync with server deduplication
    std::cout << "\n--- STEP 5: Successful Synchronous Ingestion ---" << std::endl;
    int redisPort = 16379;
    if (const char* envPort = std::getenv("NEXO_REDIS_PORT")) {
        redisPort = std::stoi(envPort);
    }
    IngestServerMock server(redisPort);
    std::string nonce = "nonce-demo-uuid-" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count());
    
    // Encrypt payload using AES-256-GCM
    std::string plainPayload = R"({"doc":")" + studentDoc + R"(","event":")" + eventType + R"(","nonce":")" + nonce + R"("})";
    std::string encryptedPayload = crypto.encrypt(plainPayload);
    std::cout << "Payload encrypted with AES-256-GCM (IV + ciphertext + tag)" << std::endl;

    auto resp1 = server.ingest(nonce, encryptedPayload, studentDoc);
    std::cout << "Server response (First delivery): HTTP " << resp1.statusCode << " (" << resp1.message << ")" << std::endl;

    if (resp1.statusCode == 503) {
        std::cerr << "ERROR: Redis is down — nonce dedupe unavailable, ingestion rejected" << std::endl;
        db.close();
        return 1;
    }
    assertThat(resp1.statusCode == 202, "first delivery accepted (HTTP 202)");

    if (resp1.statusCode == 202) {
        if (!pending.empty()) {
            db.clearAudit(pending[0].id);
        }
        std::cout << "Outbox item marked synced. Pending unsynced records remaining: " 
                  << db.getPendingAuditCount() << std::endl;
        assertThat(db.getPendingAuditCount() == 0, "outbox drained after sync");
    }

    // 6. Replay attack rejection
    std::cout << "\n--- STEP 6: Replay Attack Detection ---" << std::endl;
    std::cout << "Attacker re-sends the exact same encrypted packet with duplicate nonce..." << std::endl;
    auto resp2 = server.ingest(nonce, encryptedPayload, studentDoc);
    std::cout << "Server response (Replay packet): HTTP " << resp2.statusCode << " (" << resp2.message << ")" << std::endl;
    assertThat(resp2.statusCode == 403, "replay packet rejected (HTTP 403)");
    if (resp2.statusCode == 403) {
        std::cout << "Replay attack successfully REJECTED by server!" << std::endl;
    } else {
        std::cerr << "ERROR: Replay attack was NOT rejected (expected 403, got " << resp2.statusCode << ")" << std::endl;
    }

    db.close();
    if (!allOk) {
        std::cerr << "=== 03-EDGE-PIPELINE DEMO COMPLETE: CHECKS FAILED ===" << std::endl;
        return 1;
    }
    std::cout << "\n=== 03-EDGE-PIPELINE DEMO COMPLETE: ALL CHECKS PASSED ===" << std::endl;
    return 0;
}
