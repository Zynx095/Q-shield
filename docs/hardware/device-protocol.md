# Device protocol v1 (gateway ↔ device)

This is the contract a device must meet. The software device agent (`device_agent/`) and the ESP32 firmware
(`hardware/esp32/firmware/`) both speak it, and the gateway treats them the same. Only the `hw` label, and the
provenance shown with each trust signal, differ. The reference implementation is `backend/protocol/envelope.py`;
the payload schemas are `TelemetryPayload`, `RegisterPayload` and `HeartbeatPayload` in `backend/api/app.py`, and
`RecoveryReport` in `backend/api/security_routes.py`.

> **Status:** the software agent is tested end to end. The ESP32 firmware is a skeleton that has **not been
> compiled, flashed or run** (no board was available). The test vectors below are how to check it before it touches
> a gateway.

## 1. Envelope

Every device message is an HTTP POST of one JSON object:

```json
{"proto":1,"auth":"hmac-sha256-psk","type":"telemetry","device_id":"DEVICE-001","counter":54,
 "payload":"{\"tamper\":false,\"fw_version\":\"esp32-0.1-skeleton\",\"rssi_dbm\":-61}","tag":"<64 hex>"}
```

| Field | Rule |
|---|---|
| `proto` | `1` |
| `auth` | `hmac-sha256-psk`. This is a provisioned 32-byte secret per device. It is symmetric and **not post-quantum**. |
| `type` | `register`, `heartbeat`, `telemetry` or `recovery`. It must match the endpoint. |
| `device_id` | `[A-Za-z0-9_.-]{1,64}`. It must be enrolled (`scripts/enroll_device.py`). |
| `counter` | Integer, 0 to 2^53, **strictly greater** than the last counter the gateway accepted from this device. A lower or equal counter is rejected as a replay. |
| `payload` | The message body as JSON **text** (a string), up to 2048 bytes. The tag covers these exact bytes, so there is no canonicalisation and nothing for the two sides to disagree on. |
| `tag` | Lowercase hex HMAC-SHA256 of the signing input, keyed with the device secret. |

**Signing input** (UTF-8, `LF` = `\n`):

```
QSHIELD-V1 LF auth LF type LF device_id LF decimal(counter) LF payload
```

**Counter persistence.** A device must never reuse a counter across reboots. The firmware reserves counters ahead
of use: it persists every 50th value, and on boot it skips 51 ahead of the stored value.

## 2. Endpoints and payloads

| Endpoint | `type` | Payload fields | Notes |
|---|---|---|---|
| `POST /api/v1/register` | `register` | `fw_version` (str), `hw` (str), `capabilities` (list of str) | `hw` is `esp32` for the board and `software-agent` for the simulator. A simulator must never claim `esp32`. |
| `POST /api/v1/heartbeat` | `heartbeat` | `uptime_ms` (int) | Liveness only. |
| `POST /api/v1/telemetry` | `telemetry` | `tamper` (bool, **required**); optional: `temperature_c`, `humidity_pct`, `pressure_hpa`, `vibration_g`, `rssi_dbm` (numbers), `fw_version`, `cfg_hash` (str) | Any other field is refused (422, `malformed_payload`). An absent sensor is **left out**, never sent as 0. |
| `POST /api/v1/recovery/report` | `recovery` | The telemetry fields, plus `ack_command_id` | Only open while the device is quarantined, recovering or verified. The response may carry a remediation `command`. |

What the gateway does with each telemetry field:

| Field | Source (planned) | Used for |
|---|---|---|
| `tamper` | Reed switch on the enclosure lid | The `physical_tamper` trust signal (CRITICAL). With signed camera interference or a signed rule match inside 60 s, it gives a confirmed incident and quarantine. |
| `temperature_c`, `humidity_pct`, `pressure_hpa` | BME280 | The `sensor_out_of_range` signal, when the digital twin has a range for the field. |
| `vibration_g` | MPU6050 | As above. |
| `rssi_dbm` | Wi-Fi RSSI | Network telemetry: stored and shown in the twin. It is not scored unless an operator sets a range for it. |
| `fw_version`, `cfg_hash` | Firmware constants | The `integrity_mismatch` signal against the twin's expected values. These are **self-reported, not attestation.** |

## 3. Responses a device must handle

| Status | `detail` | Meaning | Device action |
|---|---|---|---|
| 200 | | Accepted. | Continue. |
| 401 | `authentication_failed` | Wrong tag, replayed or stale counter, unknown or revoked device. | Do not retry the same envelope. Check the secret and the counter persistence. |
| 403 | `device_quarantined` | The normal channel is closed by quarantine. | Stop normal traffic. Use the recovery channel. The skeleton firmware only backs off for 30 s. |
| 403 | `recovery_channel_not_open` | The device is not quarantined. | Use the normal channel. |
| 422 | `malformed_payload` | Authenticated, but the payload fails the schema. | A firmware bug. It costs trust (`malformed_payload`). |

Timing: the gateway marks a device offline after 15 s without an authenticated message, and the trust engine caps a
device with no authenticated message for more than 45 s at 79. Heartbeat and telemetry every 5 s keep it live.

## 4. Test vectors

- `tests/vectors/envelope_v1.json`: one telemetry message, with its signing input and tag.
- `tests/vectors/envelope_v1_cases.json`: seven messages in the order a freshly flashed board sends them:
  - register;
  - heartbeat;
  - minimal telemetry;
  - tamper open;
  - all sensors;
  - a payload with a quote and a backslash (escaping);
  - the largest counter.

  Each case gives `signing_input_hex`, `tag` and `envelope_json`, the exact bytes to POST.

Both files use a **test key** (`000102…1f`), never a real secret. `scripts/make_device_vectors.py` generates the
cases from the reference implementation. `tests/security/test_device_vectors.py` checks three things: the file is
current; every case matches the implementation byte for byte; and a gateway accepts every envelope in order, applies
the tamper report, and refuses a one-byte change or a replay.

To check firmware against the vectors, compile `hmacHex()`, `jsonEscape()` and the body builder with the test key,
the device id `DEVICE-001` and each case's counter and payload, then compare the output with `envelope_json`.
