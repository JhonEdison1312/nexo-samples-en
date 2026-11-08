#pragma once
#include <cstdint>
#include <string>
#include <vector>

/**
 * =============================================================================
 * encryption.h — Edge cryptography singleton interface.
 * =============================================================================
 * RESPONSIBILITY:
 *   Provides AES-256-GCM operations and API key/token management in a
 *   singleton. On initialization it recovers the AES key from a protected
 *   file (not the local database) and the API token from SQLite; when
 *   provisioning them it persists them in those same places. The key is
 *   kept in memory with mlock() when possible and wiped with
 *   OPENSSL_cleanse.
 *
 * ENCRYPTION FLOW:
 *   plaintext + IV(12 random)
 *        │
 *        ▼
 *   AES-256-GCM -> ciphertext + tag(16)
 *        │
 *        ▼
 *   packed = IV + ciphertext + tag  -> base64Encode
 *
 * DEPENDENCIES:
 *   - OpenSSL (EVP_aes_256_gcm, RAND_bytes, BIO base64, mlock/munlock).
 *   - base_de_datos/sqlite_manager.h (for initialize()).
 */
class Encryption {
public:
    static Encryption& getInstance() {
        static Encryption instance;
        return instance;
    }

    bool initialize();
    void setKeyFile(const std::string& path);

    // Key provisioning
    bool isKeyProvisioned() const;
    bool isTokenProvisioned() const;
    bool provisionKey(const std::string& key);
    bool provisionToken(const std::string& token);

    // AES-256-GCM
    std::string encrypt(const std::string& plaintext);
    std::string encrypt(const std::string& plaintext, const std::vector<uint8_t>& iv);
    std::string decrypt(const std::string& ciphertext);

    // Keyed hash (HMAC-SHA256 hex, deterministic) for fields used
    // as lookup keys (e.g. document). Returns "" when unavailable
    // provisioned key — the caller decides the degradation.
    std::string keyedHash(const std::string& plaintext);

    // Token
    std::string getToken() const;

private:
    Encryption() = default;
    ~Encryption();
    std::vector<char> m_aesKey;
    std::string m_apiToken;
    std::string m_keyFile = "nexo_edge.key";

    bool saveKeyToFile(const std::string& key);
    bool loadKeyFromFile(std::string& key);

    // Hardware binding — encrypt the AES key on disk with a CPU-serial-derived key
    std::string getHardwareBoundKey();  // Deriva clave de /proc/cpuinfo (Serial + Revision)
    bool saveKeyToFileEncrypted(const std::string& key);
    bool loadKeyFromFileEncrypted(std::string& key);
};

