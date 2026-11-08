#pragma once

/**
 * =============================================================================
 * INotification.h — Abstract audible/visual notification interface.
 * =============================================================================
 * RESPONSIBILITY:
 *   Contract for emitting success, error or warning signals. Allows stub
 *   implementations or real ones with GPIO/buzzer/LEDs (RealGpioManager).
 */
class INotification {
public:
    virtual ~INotification() = default;
    virtual void notifySuccess() = 0;
    virtual void notifyError() = 0;
    virtual void notifyWarning() = 0;

    // Light/sound pattern for the node power state.
    // state: 0=MAINS, 1=BATTERY, 2=LOW_BATTERY, 3=CRITICAL (orden de PowerState).
    virtual void notifyPowerState(int /*state*/) {}

    // Active fan control (GPIO fan). No-op in stubs.
    virtual void setFan(bool /*on*/) {}
};

