#pragma once
#include <string>
#include <vector>
#include <cstdint>
#include <sqlite3.h>

/**
 * =============================================================================
 * sqlite_manager.h — Interfaz singleton de la base de datos local SQLite.
 * =============================================================================
 * RESPONSIBILITY:
 *   Holds the edge device local storage: students, attendance patterns,
 *   absences (legacy), audit_trail for pending uploads and a config
 *   (key/value) table. All fingerprint templates are encrypted with
 *   Encryption before being stored and decrypted when read.
 *
 * TABLES:
 *   - estudiantes: documento (PK), nombre, phone/guardian name, huella_id,
 *     template_huella (base64 encrypted).
 *   - patrones: early/late arrival summary per student.
 *   - inasistencias: legacy (not implemented in cpp).
 *   - audit_trail: local events pending sync to the cloud.
 *   - config: key/value pairs (AES key, token, etc.).
 *
 * DEPENDENCIAS:
 *   - sqlite3
 *   - base_de_datos/encryption.h (cifrado de templates)
 *   - openssl/rand.h (IV aleatorio para templates)
 */
struct Estudiante {
    std::string documento;
    std::string nombre;
    std::string telefono_acudiente;
    std::string nombre_acudiente;
    uint32_t huella_id = 0;
    std::vector<uint8_t> template_huella;
    std::string school_id;  // Multi-tenancy: school identifier
};

struct AuditRecord {
    int id;
    std::string documento;
    std::string event;
    int timestamp;
    int attempts;
};

class SqliteManager {
public:
    static SqliteManager& getInstance() {
        static SqliteManager instance;
        return instance;
    }

    bool initialize(const std::string& dbPath = "nexo_edge.db");
    void close();
    bool factoryReset();

    // Students
    bool saveEstudiante(const Estudiante& est);
    bool getEstudianteByDocumento(const std::string& doc, Estudiante& est);
    bool getEstudianteByHuellaID(uint32_t huellaId, Estudiante& est);
    bool deleteEstudiante(const std::string& doc);
    uint32_t getNextHuellaID();

    // Multi-fingerprint (up to 2 fingers per student)
    bool saveHuella(const std::string& doc, int fingerSlot, uint32_t huellaId,
                    const std::vector<uint8_t>& tpl, const std::string& schoolId);
    int  getHuellaCount(const std::string& doc);
    bool getHuellaIdsByDocumento(const std::string& doc, std::vector<uint32_t>& idsOut);
    bool huellaSlotExists(const std::string& doc, int fingerSlot);

    // Attendance patterns (UPSERT)
    bool updatePattern(const std::string& documento, bool temprano, bool tarde);
    bool getPatternSummary(const std::string& documento, int& temprano, int& tarde, int& total);

    // PAE
    bool savePAE(const std::string& documento, bool recibido);

    // Absence tracking
    bool checkInasistencia(const std::string& documento);
    bool deleteInasistencia(const std::string& documento);

    // Audit trail
    bool saveAudit(const std::string& documento, const std::string& event);
    bool getPendingAudits(std::vector<AuditRecord>& audits);
    bool clearAudit(int id);
    bool clearAudit(const std::string& documento, const std::string& event); // Keep for compatibility
    bool incrementAuditAttempt(int id);
    bool markAuditError(int id);
    // Purge old synced or DLQ records to avoid filling the SD card
    int purgeOldAuditTrail(int daysSynced = 30, int daysDlq = 90);
    // Queue metrics for telemetry
    int getPendingAuditCount();
    int getDlqCount();
    // Long-term requeue — reactivates synced=-1 records (SyncWorker, ~1h)
    int requeueDlqItems(int limit = 20);
    // VACUUM to reclaim physical space after purging
    bool vacuum();

    // Bulk load for biometric cache
    bool getAllEstudiantesConTemplate(std::vector<Estudiante>& estudiantes);

    // Config KV store
    bool setConfig(const std::string& key, const std::string& value);
    std::string getConfig(const std::string& key, const std::string& defaultVal = "");

    sqlite3* getDB() { return db; }

private:
    SqliteManager() = default;
    ~SqliteManager() { close(); }
    sqlite3* db = nullptr;
    bool createTables();
    void migrateSchema();  // Migrations for existing databases
};

