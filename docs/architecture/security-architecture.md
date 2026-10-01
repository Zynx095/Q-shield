

## Operator identity, authorization and transport (Phase 13)
| Layer | Implemented | Prototype limitation |
|---|---|---|
| Identity | named operators; `qso_` 256-bit bearer tokens; SHA-256 stored; revoke and expiry | bearer = identity; no MFA; bootstrap shared token on by default |
| Authorization | roles viewer < operator < admin, checked per route (403 + `operator_forbidden` event) | global roles, not per device |
| Attribution | `operator_action` security event + ML-DSA evidence entry for every action, success or refusal | evidence chain not externally anchored (TD-09) |
| Transport | HTTPS through uvicorn with a configured cert/key; `QSHIELD_REQUIRE_TLS` | self-signed dev cert, no PKI/mTLS; ESP32 uses HMAC over HTTP |
