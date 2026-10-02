# Wiring plan (interface level)

> **Planned, not built.** The ESP32 board variant has not been identified, so this plan names **buses and
> signals, not pin numbers**. Pin numbers go in `hardware/esp32/firmware/include/board.h` once the board is in
> hand. That file is not in the repository; the firmware compiles telemetry only when it exists.

| Part (bill-of-materials.md) | Interface | Signal to the firmware | Telemetry field | Notes |
|---|---|---|---|---|
| Reed switch + magnet | One GPIO with `INPUT_PULLUP`; the switch goes to GND | `QSHIELD_TAMPER_PIN`; `QSHIELD_TAMPER_OPEN_LEVEL` (default `HIGH`: the magnet away means open) | `tamper` | Mount the magnet on the lid. Verify the open and closed levels on the real switch (normally open or normally closed) before trusting them. Avoid strapping pins. |
| BME280 | I2C (SDA, SCL), 3.3 V | Default address 0x76 or 0x77 | `temperature_c`, `humidity_pct`, `pressure_hpa` | Shares the bus with the MPU6050 and the OLED. |
| MPU6050 | I2C, 3.3 V | Default address 0x68 | `vibration_g` (acceleration magnitude minus gravity, over a short window) | Define the computation in firmware, then measure the normal range before setting a twin range. |
| SSD1306 OLED | I2C, 3.3 V | Address 0x3C | none | Local status only. It is never a source of evidence. |
| RGB LED, buzzer | GPIO (with series resistors for the LED) | none yet | none | Local indication of the trust state. The device would need to read its state. Not designed. |
| Push buttons | GPIO with `INPUT_PULLUP` | none yet | none | Must never clear a tamper or quarantine locally: recovery is gateway-driven. |
| ESP32-CAM (if used) | Wi-Fi MJPEG stream | none | none | Read by the vision service as `camera.source = "http://<ip>:81/stream"`. A separate board from the sensor ESP32 is simpler. |

Bring-up order: reed switch first (it drives the strongest trust signal), then the BME280, then the MPU6050. After
each step, compare the dashboard's twin view with the physical state.
