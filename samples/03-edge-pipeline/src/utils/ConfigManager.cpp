/**
 * =============================================================================
 * ConfigManager.cpp — JSON configuration singleton implementation.
 * =============================================================================
 * RESPONSIBILITY:
 *   Loads config.json from disk (with fallback to default values) and
 *   provides typed getters (string, int, bool). If the file is missing or
 *   invalid, defaults are returned and a warning is logged.
 */

#include "utils/ConfigManager.h"
#include "utils/Logger.h"
#include <fstream>
#include <regex>

bool ConfigManager::loadConfig(const std::string& path) {
    std::ifstream file(path);
    std::lock_guard<std::mutex> lock(m_mutex);
    m_configPath = path;  // save path for saveConfig
    if (!file.is_open()) {
        LOG_WARN("Config file '{}' not found, using defaults", path);
        m_config = nlohmann::json::object();
        return false;
    }
    try {
        m_config = nlohmann::json::parse(file);
        LOG_INFO("Config loaded from '{}'", path);
        return true;
    } catch (const nlohmann::json::exception& e) {
        LOG_ERROR("Config parse error: {}", e.what());
        m_config = nlohmann::json::object();
        return false;
    }
}

// Persist config to disk (atomic write temp->rename)
bool ConfigManager::saveConfig(const std::string& path) {
    std::lock_guard<std::mutex> lock(m_mutex);
    std::string outPath = path.empty() ? m_configPath : path;
    if (outPath.empty()) {
        LOG_ERROR("[ConfigManager] No config path set for saveConfig");
        return false;
    }
    std::string tmpPath = outPath + ".tmp";
    {
        std::ofstream ofs(tmpPath, std::ios::trunc);
        if (!ofs) {
            LOG_ERROR("[ConfigManager] Cannot open '{}' for writing", tmpPath);
            return false;
        }
        ofs << m_config.dump(2) << std::endl;
        if (!ofs) {
            LOG_ERROR("[ConfigManager] Write failed to '{}'", tmpPath);
            return false;
        }
        ofs.close();
    }
    if (std::rename(tmpPath.c_str(), outPath.c_str()) != 0) {
        LOG_ERROR("[ConfigManager] Failed to rename '{}' -> '{}'", tmpPath, outPath);
        return false;
    }
    LOG_INFO("[ConfigManager] Config saved to '{}'", outPath);
    return true;
}

// Update a value in memory and optionally persist it
bool ConfigManager::setValue(const std::string& key, const std::string& value, bool persist) {
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_config[key] = value;
    }
    if (persist) return saveConfig();
    return true;
}

// Validates UUID v4 format (what the API expects)
bool ConfigManager::isValidUuidV4(const std::string& id) {
    if (id.empty()) return false;
    // UUID v4 regex: 8-4-4-4-12 hex, version 4, variant 8/9/a/b
    static const std::regex uuidV4Regex(
        "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        std::regex::icase);
    return std::regex_match(id, uuidV4Regex);
}

std::string ConfigManager::getString(const std::string& key, const std::string& defaultVal) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_config.contains(key) && m_config[key].is_string())
        return m_config[key].get<std::string>();
    return defaultVal;
}

int ConfigManager::getInt(const std::string& key, int defaultVal) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_config.contains(key) && m_config[key].is_number_integer())
        return m_config[key].get<int>();
    return defaultVal;
}

bool ConfigManager::getBool(const std::string& key, bool defaultVal) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_config.contains(key) && m_config[key].is_boolean())
        return m_config[key].get<bool>();
    return defaultVal;
}

