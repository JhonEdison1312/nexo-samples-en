#pragma once

/**
 * =============================================================================
 * BiometricLockout.h — Software anti-spoof lockout (G-2).
 * =============================================================================
 * RESPONSIBILITY:
 *   Counts rejected finger presentations (captured print with no match —
 *   NexoError::NoMatch in both sensors) over a sliding window. Past the
 *   threshold it imposes a cooldown during which the attendance loop does not
 *   query the sensor. Slows down template guessing and fake fingers without
 *   depending on hardware anti-spoof.
 *
 *   The clock is injected as a parameter so tests can advance time without
 *   sleeps. It has no on-disk state: after reboot the counter resets to zero —
 *   the lockout is a pacing defense, not a persistent sanction.
 */
#include <chrono>

class BiometricLockout {
public:
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;

    BiometricLockout(int maxFails = 8, int windowSec = 120, int cooldownSec = 60)
        : m_maxFails(maxFails), m_window(windowSec), m_cooldown(cooldownSec) {}

    // Records a rejected finger. Returns true only on the attempt that crosses
    // the threshold (single point to audit/alert). Rejections during the
    // lockout neither extend nor re-trigger it.
    bool registerFailure(TimePoint now) {
        if (isLocked(now)) return false;
        if (now - m_windowStart > m_window) {
            m_windowStart = now;
            m_fails = 0;
        }
        if (++m_fails >= m_maxFails) {
            m_lockedUntil = now + m_cooldown;
            m_fails = 0;
            m_windowStart = now;
            return true;
        }
        return false;
    }

    // A valid match resets the window — normal use never accumulates.
    void registerSuccess(TimePoint now) {
        m_fails = 0;
        m_windowStart = now;
    }

    bool isLocked(TimePoint now) const { return now < m_lockedUntil; }

    int cooldownRemainingSec(TimePoint now) const {
        auto rem = std::chrono::duration_cast<std::chrono::seconds>(m_lockedUntil - now).count();
        return rem > 0 ? static_cast<int>(rem) : 0;
    }

    int failures() const { return m_fails; }

private:
    int m_maxFails;
    std::chrono::seconds m_window;
    std::chrono::seconds m_cooldown;
    int m_fails = 0;
    TimePoint m_windowStart{};
    TimePoint m_lockedUntil{};
};

