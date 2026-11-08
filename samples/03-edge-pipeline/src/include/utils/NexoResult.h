#pragma once

#include <string>
#include <optional>

/**
 * =============================================================================
 * NexoResult.h — Edge result monad and error enumeration.
 * =============================================================================
 * RESPONSIBILITY:
 *   Defines NexoError (typical edge errors) and the NexoResult<T> template
 *   wrapping an optional value, an error code and a message. Includes the
 *   NexoResult<void> specialization for operations with no return value.
 */
enum class NexoError {
    None,
    NotInitialized,
    SensorError,
    BadQuality,
    NoMatch,
    Timeout,
    DatabaseError,
    NetworkError,
    CryptoError,
    InvalidInput,
    PermissionDenied,
    Cancelled,  // Capture cancelled by cancelCapture()
    Unknown
};

inline std::string toString(NexoError e) {
    switch (e) {
        case NexoError::None:             return "None";
        case NexoError::NotInitialized:   return "NotInitialized";
        case NexoError::SensorError:      return "SensorError";
        case NexoError::BadQuality:       return "BadQuality";
        case NexoError::NoMatch:          return "NoMatch";
        case NexoError::Timeout:          return "Timeout";
        case NexoError::DatabaseError:    return "DatabaseError";
        case NexoError::NetworkError:     return "NetworkError";
        case NexoError::CryptoError:      return "CryptoError";
        case NexoError::InvalidInput:     return "InvalidInput";
        case NexoError::PermissionDenied: return "PermissionDenied";
        case NexoError::Cancelled:        return "Cancelled";
        case NexoError::Unknown:          return "Unknown";
    }
    return "Unknown";
}

template <typename T>
struct NexoResult {
    NexoError error = NexoError::None;
    std::string message;
    std::optional<T> value;

    explicit operator bool() const { return error == NexoError::None; }

    static NexoResult success(T val) {
        return {NexoError::None, "", std::move(val)};
    }
    static NexoResult fail(NexoError err, std::string msg = "") {
        return {err, std::move(msg), std::nullopt};
    }
};

template <>
struct NexoResult<void> {
    NexoError error = NexoError::None;
    std::string message;

    explicit operator bool() const { return error == NexoError::None; }

    static NexoResult success() {
        return {NexoError::None, ""};
    }
    static NexoResult fail(NexoError err, std::string msg = "") {
        return {err, std::move(msg)};
    }
};

