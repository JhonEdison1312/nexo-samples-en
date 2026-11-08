/**
 * =============================================================================
 * DevStubBiometricSensor.cpp — Stub implementation of the biometric sensor.
 * =============================================================================
 * RESPONSIBILITY:
 *   Simulates a biometric sensor for hardware-free testing. Immediate
 *   initialization, enrollment returns a dummy template, search simulates a
 *   match every 5 attempts with a 500 ms delay.
 */

#include "hardware/dev_stub/DevStubBiometricSensor.h"
#include "utils/Logger.h"
#include <thread>
#include <chrono>

NexoResult<void> DevStubBiometricSensor::initialize() {
    LOG_INFO("[STUB] Biometric sensor initialized (dev-stub)");
    m_ready = true;
    return NexoResult<void>::success();
}

NexoResult<void> DevStubBiometricSensor::enrollUser(uint32_t userId, std::vector<uint8_t>& templateOut) {
    if (!m_ready) return NexoResult<void>::fail(NexoError::NotInitialized, "Sensor not initialized");
    LOG_INFO("[STUB] Enroll user ID={}", userId);
    templateOut.assign(256, 0xAA);
    return NexoResult<void>::success();
}

NexoResult<void> DevStubBiometricSensor::searchUser(const std::vector<uint8_t>& /*templateData*/,
                                                     uint32_t& matchedUserId, float& matchScore) {
    if (!m_ready) return NexoResult<void>::fail(NexoError::NotInitialized, "Sensor not initialized");

    // Realistic delay to simulate sensor processing
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Simulate that no fingerprint is present most of the time (1 match out of 5 attempts)
    static int count = 0;
    if (++count % 5 == 0) {
        LOG_DEBUG("[STUB] Search user (simulated match ID=1)");
        matchedUserId = 1;
        matchScore = 95.0f;
        return NexoResult<void>::success();
    }

    LOG_DEBUG("[STUB] Search user (no match - stub)");
    return NexoResult<void>::fail(NexoError::NoMatch, "No match (stub)");
}

NexoResult<void> DevStubBiometricSensor::deleteUser(uint32_t userId) {
    if (!m_ready) return NexoResult<void>::fail(NexoError::NotInitialized, "Sensor not initialized");
    LOG_INFO("[STUB] Delete user ID={}", userId);
    return NexoResult<void>::success();
}

