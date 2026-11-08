#pragma once
#include "hal/IHttpClient.h"

/**
 * =============================================================================
 * DevStubHttpClient.h — Stub HTTP client implementation.
 * =============================================================================
 * RESPONSIBILITY:
 *   IHttpClient implementation that simulates a successful HTTP response
 *   without any network connection. Allows testing CloudManager offline.
 */
class DevStubHttpClient : public IHttpClient {
public:
    bool postRequest(const std::string& url,
                     const std::string& body,
                     const std::map<std::string, std::string>& headers,
                     std::string& response) override;
};

