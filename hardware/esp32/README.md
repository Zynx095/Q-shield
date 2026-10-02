# ESP32 endpoint

**Status: board not yet identified; firmware is an untested skeleton.**

- No ESP32 was connected during Phase 0/1, so the exact board/variant is unknown. Nothing here
  assumes a variant, an ESP32-CAM, or a pin mapping. `firmware/platformio.ini` uses the generic
  `esp32dev` target as a placeholder.
- **Before hardware-specific work:** connect the board, identify it (`pio device list`,
  `esptool chip_id`), record it in this file, then define the sensor pin map from the real wiring.
- `firmware/src/main.cpp` implements Wi-Fi, HMAC-SHA256 device authentication and
  register/heartbeat. Telemetry (reed switch and Wi-Fi RSSI) is compiled only once `include/board.h`
  defines `QSHIELD_TAMPER_PIN` for real wiring, so no invented values or tamper state are ever sent.
  It has **not been compiled or run**. The first step is to reproduce `tests/vectors/envelope_v1.json`
  and `tests/vectors/envelope_v1_cases.json` byte for byte.
- The contract is `docs/hardware/device-protocol.md`. The bring-up order and what stays unchanged on the
  gateway are in `docs/hardware/hardware-architecture.md`. The interface-level wiring is in
  `docs/hardware/wiring-plan.md`.
- Device authentication is a provisioned symmetric HMAC-SHA256 secret. It is **not post-quantum**.
  The ESP32 does not run ML-KEM/ML-DSA.
- Credentials: `python scripts/enroll_device.py DEVICE-001 --esp32-secrets hardware/esp32/firmware/include/secrets.h --wifi-ssid ... --gateway-host <laptop hostname or IP>`
  (the generated file is gitignored). PlatformIO Core 6.2 is installed on the dev laptop, but the espressif32
  platform is not, so the firmware has not been built.
