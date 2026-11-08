#pragma once

#include <string>
#include <mutex>
#include <nlohmann/json.hpp>

/**
 * =============================================================================
 * ConfigManager.h — Edge JSON configuration singleton.
 * =============================================================================
 * RESPONSIBILITY:
 *   Loads config.json (by default) and provides typed access to config
 *   values: api_url, db_path, log_path, device_id, device_token, mqtt_host,
 *   sensor_match_threshold, etc. Missing values return their documented default.
 *
 * DEFAULT FILE:
 *   - config.json (relative to the working directory)
 *   - /opt/nexo/config.json for RPi deployments
 */
class ConfigManager {
public:
    static ConfigManager& getInstance() {
        static ConfigManager instance;
        return instance;
    }

    bool loadConfig(const std::string& path = "config.json");
    // Persist updated config to disk (for device_id auto-update)
    bool saveConfig(const std::string& path = "");
    // Update a value in memory and optionally persist it
    bool setValue(const std::string& key, const std::string& value, bool persist = false);

    std::string getString(const std::string& key, const std::string& defaultVal = "") const;
    int getInt(const std::string& key, int defaultVal = 0) const;
    bool getBool(const std::string& key, bool defaultVal = false) const;

    // Convenience accessors
    std::string getApiUrl() const { return getString("api_url", ""); }
    std::string getDbPath() const { return getString("db_path", "nexo_edge.db"); }
    std::string getLogPath() const { return getString("log_path", "nexo-edge.log"); }
    std::string getLogLevel() const { return getString("log_level", "info"); }
    std::string getDeviceId() const { return getString("device_id", ""); }
    std::string getDeviceToken() const { return getString("device_token", ""); }
    int getMatchThreshold() const { return getInt("sensor_match_threshold", 45); }

    // Valida que device_id sea UUID v4 (formato API)
    static bool isValidUuidV4(const std::string& id);

private:
    ConfigManager() = default;
    mutable std::mutex m_mutex;
    nlohmann::json m_config;
    std::string m_configPath = "config.json";  // path for saveConfig
};

