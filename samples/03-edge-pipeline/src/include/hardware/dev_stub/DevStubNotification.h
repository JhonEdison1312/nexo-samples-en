#pragma once
#include "hal/INotification.h"

/**
 * =============================================================================
 * DevStubNotification.h — Stub notification implementation.
 * =============================================================================
 * RESPONSIBILITY:
 *   INotification implementation that emits beep logs instead of driving
 *   real GPIO, buzzer or LEDs. Used in development mode.
 */
class DevStubNotification : public INotification {
public:
    void notifySuccess() override;
    void notifyError() override;
    void notifyWarning() override;
};

