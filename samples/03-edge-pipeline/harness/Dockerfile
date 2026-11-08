# ADDED FOR THIS SAMPLE
FROM gcc:12.3.0-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-dev \
    libssl-dev \
    libcurl4-openssl-dev \
    libspdlog-dev \
    libfmt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY src /app/src
COPY harness /app/harness

RUN g++ -std=c++20 -Wall -Wextra -Wpedantic \
    -I /app/src/include \
    -I /app/src \
    -I /app/harness/include \
    /app/src/encryption.cpp \
    /app/src/sqlite_manager.cpp \
    /app/src/DevStubBiometricSensor.cpp \
    /app/src/cloud_manager.cpp \
    /app/src/utils/ConfigManager.cpp \
    /app/harness/main_demo.cpp \
    -lsqlite3 -lcrypto -lssl -lcurl -lspdlog -lfmt \
    -o /app/edge_demo

CMD ["/app/edge_demo"]
