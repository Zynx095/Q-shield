# ESP32 endpoint

**Status: board not yet identified; firmware is an untested skeleton.**

- No ESP32 was connected during Phase 0/1, so the exact board/variant is unknown. Nothing here
  assumes a variant, an ESP32-CAM, or a pin mapping. `firmware/platformio.ini` uses the generic
  `esp32dev` target as a placeholder.
- **Before hardware-specific work:** connect the board, identify it (`pio device list`,
  `esptool chip_id`), record it in this file, then define the sensor pin map from the real wiring.
- `firmware/src/main.cpp` implements Wi-Fi, HMAC-SHA256 device authentication and
  register/heartbeat only. It has **not been compiled or run**; the first step is to check its HMAC
  against `tests/vectors/envelope_v1.json`. Telemetry is intentionally absent until real sensors
  (BME280, MPU6050, reed switch) are wired, so no invented values or tamper state are ever sent.
- Device authentication is a provisioned symmetric HMAC-SHA256 secret. It is **not post-quantum**.
  The ESP32 does not run ML-KEM/ML-DSA.
- Credentials: `python scripts/enroll_device.py DEVICE-001 --esp32-secrets hardware/esp32/firmware/include/secrets.h --wifi-ssid ... --gateway-host <laptop hostname or IP>`
  (the generated file is gitignored). PlatformIO is not installed on the dev laptop yet.
