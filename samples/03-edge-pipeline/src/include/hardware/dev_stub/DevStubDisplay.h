#pragma once
#include "hal/IDisplay.h"

/**
 * =============================================================================
 * DevStubDisplay.h — Stub display implementation.
 * =============================================================================
 * RESPONSIBILITY:
 *   IDisplay implementation that redirects messages to the logger instead of
 *   updating real hardware. Useful for testing on machines without OLED.
 */
class DevStubDisplay : public IDisplay {
public:
    void showMessage(const std::string& line1, const std::string& line2 = "") override;
    void clear() override;
};

