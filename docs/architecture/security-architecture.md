

## Operator identity, authorization and transport (Phase 13)
| Layer | Implemented | Prototype limitation |
|---|---|---|
| Identity | named operators; `qso_` 256-bit bearer tokens; SHA-256 stored; revoke and expiry | bearer = identity; no MFA; bootstrap shared token on by default |
| Authorization | roles viewer < operator < admin, checked per route (403 + `operator_forbidden` event) | global roles, not per device |
| Attribution | `operator_action` security event + ML-DSA evidence entry for every action, success or refusal | evidence chain not externally anchored (TD-09) |
| Transport | HTTPS through uvicorn with a configured cert/key; `QSHIELD_REQUIRE_TLS` | self-signed dev cert, no PKI/mTLS; ESP32 uses HMAC over HTTP |

## Abuse resistance (Phase 17)
| Threat | Control | Residual risk |
|---|---|---|
| Unauthenticated flood growing the database | `RejectionRecorder`: 3 samples per (event type, claimed identity) per 10 s, at most 120 per window; the rest coalesced into one row with the count; routine rows beyond 20 000 pruned once consumed by the trust engine; high-value events never sampled | coalesced counts held in memory are lost if the gateway stops; identities beyond the window cap share one unattributed row |
| Trust denial by forged traffic | pressure capped at 25 points (never quarantine); sampling keeps the pressure, the repeated-replay hold and the "no credit after a violation" rule exactly as before (tested against unsampled runs) | a network attacker can still hold a device at SUSPICIOUS |
| ML-KEM session-table exhaustion by a misbehaving client | gateway cap of 64 live sessions; the vision client re-handshakes only on `session_expired`, backs off (1 s to 60 s) and is limited to 20 handshakes per hour | a client holding a valid signer key can still open sessions up to the gateway cap |
| Camera blinded, turned, frozen or replaced | the vision service reports it, signed; the trust engine penalises it, and confirms an incident together with a tamper report | thresholds unvalidated; a slow or small change, or one made before the reference view is learned, is missed; a compromised vision key can also lie about the camera |
