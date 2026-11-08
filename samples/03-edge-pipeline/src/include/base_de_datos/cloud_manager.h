#pragma once
#include <string>
#include "base_de_datos/encryption.h"
#include "hal/IHttpClient.h"

/**
 * =============================================================================
 * cloud_manager.h — Cloud sync manager interface (CloudManager).
 * =============================================================================
 * RESPONSIBILITY:
 *   Singleton interface to sync attendance records and run cloud commands
 *   (register/delete students/staff, wipe, verify institutions/groups).
 *   Builds authenticated requests by encrypting the payload JSON with
 *   AES-256-GCM and sending it via libcurl (or an injected IHttpClient
 *   for testing).
 *
 * TYPICAL FLOW (syncRecord):
 *   syncRecord(jsonData)
 *        │
 *        ▼
 *   buildAuthenticatedRequest(jsonData, instId)
 *        │  ├─ Encrypts payload with Encryption (AES-256-GCM)
 *        │  └─ Adds inst_id, optional token, base64 payload
 *        ▼
 *   curlPost / httpClientPost(m_httpClient)
 *        │  ├─ Headers: Content-Type, User-Agent, X-NEXO-TOKEN
 *        │  └─ Checks HTTP 200 or 202
 *        ▼
 *   returns ok/fail
 *
 * DEPENDENCIES:
 *   - base_de_datos/encryption.h  : AES-256-GCM and token.
 *   - hal/IHttpClient.h           : HTTP abstraction for dev stubs/tests.
 *   - libcurl                     : real transport on Linux/RPi4.
 *
 * CONFIGURATION:
 *   - NEXO_API_URL (env) or /opt/nexo/config.json api_url.
 *   - m_instId set via setInstitutionId().
 */
class CloudManager {
public:
    static CloudManager& getInstance() {
        static CloudManager instance;
        return instance;
    }

    bool syncRecord(const std::string& jsonData);

    bool registerStudent(const std::string& doc, const std::string& nombre, const std::string& tel,
                         const std::string& salon, const std::string& parent_doc, const std::string& parent_name);
    bool registerStudentWithFingerprint(const std::string& doc, const std::string& nombre,
                                        const std::string& tel, uint32_t huellaId, int fingerSlot = 1);
    bool registerStaff(const std::string& doc, const std::string& nombre, const std::string& tel,
                       const std::string& rol, const std::string& jornada);
    bool deleteStudent(const std::string& doc);
    bool wipeInstitution(const std::string& instId);
    std::string verifyInstitution(const std::string& nombre);
    bool verifyGroup(const std::string& instId, const std::string& salon);

    void setInstitutionId(const std::string& id) { m_instId = id; }
    std::string getInstitutionId() const { return m_instId; }

    void setHttpClient(IHttpClient* client) { m_httpClient = client; }

private:
    CloudManager();
    std::string m_apiUrl;
    std::string m_instId = "";
    IHttpClient* m_httpClient = nullptr; // nullptr = usar libcurl real

    std::string buildAuthenticatedRequest(const std::string& jsonData, const std::string& instId);
    std::string loadApiUrl();
    std::string getIngestUrl() const;
};

