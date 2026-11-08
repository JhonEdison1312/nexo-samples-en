#pragma once
#include <string>
#include <map>

/**
 * =============================================================================
 * IHttpClient.h — Abstract HTTP client interface.
 * =============================================================================
 * RESPONSIBILITY:
 *   Abstraction for performing HTTP POSTs with custom headers. Allows
 *   replacing libcurl with a stub in unit tests or network-less environments.
 *
 * IMPLEMENTATIONS:
 *   - DevStubHttpClient : responds {"status":"ok","stub":true} without leaving.
 *   - CloudManager::curlPost (does not implement IHttpClient).
 */
class IHttpClient {
public:
    virtual ~IHttpClient() = default;
    virtual bool postRequest(const std::string& url,
                             const std::string& body,
                             const std::map<std::string, std::string>& headers,
                             std::string& response) = 0;
};

