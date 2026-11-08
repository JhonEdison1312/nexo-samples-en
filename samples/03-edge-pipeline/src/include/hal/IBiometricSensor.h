#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include "utils/NexoResult.h"

/**
 * =============================================================================
 * IBiometricSensor.h — Abstract interface for the biometric sensor.
 * =============================================================================
 * RESPONSIBILITY:
 *   Defines the contract any biometric sensor (real or stub) must fulfill:
 *   initialization, enrollment, 1:N search, user deletion and status query.
 *   Allows injecting DevStub or ZK9500 implementations without touching main.cpp.
 *
 * FLOW:
 *   initialize() -> isReady()
 *        │
 *        ├── enrollUser(userId, templateOut) -> store encrypted template
 *        └── searchUser(templateData, matchedUserId, matchScore) -> identify
 *
 * IMPLEMENTATIONS:
 *   - hardware/dev_stub/DevStubBiometricSensor : simulation without hardware.
 *   - hardware/real/Zk9500BiometricSensor      : ZKTeco ZK9500 sensor.
 */
class IBiometricSensor {
public:
    virtual ~IBiometricSensor() = default;

    virtual NexoResult<void> initialize() = 0;

    virtual NexoResult<void> enrollUser(uint32_t userId, std::vector<uint8_t>& templateOut) = 0;

    // Adds an already-generated template to the sensor cache. Enables atomic enrollment:
    // SQLite first, cache second. Default no-op implementation for stubs.
    virtual NexoResult<void> addTemplate(uint32_t userId, const std::vector<uint8_t>& templateData) {
        (void)userId;
        (void)templateData;
        return NexoResult<void>::success();
    }

    virtual NexoResult<void> searchUser(const std::vector<uint8_t>& templateData,
                                        uint32_t& matchedUserId,
                                        float& matchScore) = 0;

    virtual NexoResult<void> deleteUser(uint32_t userId) = 0;

    // Cancels a blocking capture (e.g. dpfpdd_cancel). No-op by default.
    virtual void cancelCapture() {}

    virtual bool isReady() const = 0;
    virtual std::string getLastError() const = 0;
};

