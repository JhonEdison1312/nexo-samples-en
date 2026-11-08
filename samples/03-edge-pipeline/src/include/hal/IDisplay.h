#pragma once
#include <string>

/**
 * =============================================================================
 * IDisplay.h — Abstract interface for the edge display/screen.
 * =============================================================================
 * RESPONSIBILITY:
 *   Minimal contract to show two-line messages and clear the screen.
 *   Implemented by DevStubDisplay (logs) and RealOledDisplay (SSD1306 I2C).
 */
class IDisplay {
public:
    virtual ~IDisplay() = default;
    virtual void showMessage(const std::string& line1, const std::string& line2 = "") = 0;
    virtual void clear() = 0;
};

