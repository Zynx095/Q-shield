# PQC module (Phase 3)

Status: **implemented and tested on the laptop side.** ML-KEM-768 and ML-DSA-65 are used by the gateway and the vision service. **The ESP32 does not run any PQC**; it authenticates with a provisioned HMAC-SHA256 secret, which is **not post-quantum**. ESP32 PQC feasibility is a separate research item and is not implemented.

## Security domains (do not blur)

| Component | Authentication / protection | Post-quantum? |
|---|---|---|
| ESP32 device | per-device HMAC-SHA256 envelope (`hmac-sha256-psk`), counter replay protection, no confidentiality | **No** (symmetric) |
| Vision service (software, laptop) | ML-DSA-65 signatures over each observation; optional ML-KEM-768 session with AES-256-GCM | Yes, where the signed/secure endpoints are used |
| Gateway | verifies ML-DSA signatures; terminates ML-KEM sessions (static ML-KEM-768 key) | Yes, on those endpoints only |
| Operator/ingest bearer tokens, DB credential encryption | tokens / AES-256-GCM | No (classical; AES-256 is not what "PQC" means) |
| Unsigned `POST /api/v1/observations` | ingest bearer token only | **No**; stored with `auth: "ingest-token"` and can be disabled (`REQUIRE_SIGNED_OBSERVATIONS=true`) |

The system as a whole is not "PQC-secured": only the vision-service to gateway observation path is, and the identity belongs to the **vision software service**, not to the USB webcam (which has no cryptographic identity).

## Algorithms, library, source

| Item | Value |
|---|---|
| Key establishment | ML-KEM-768 (FIPS 203) |
| Signatures | ML-DSA-65 (FIPS 204), external interface, pure mode, context string used for domain separation |
| Library | `pqcrypto` **1.0.0** (Backbone Technologies Ltd., PyPI, Apache-2.0) |
| Implementation source | Rust crates `backbone-ml-kem` 0.2.0 / `backbone-ml-dsa` 0.2.0 (from the wheel's SBOM), Python bindings via PyO3. This project did not audit them. |
| Platform verified | Windows 11 x86-64, Python 3.12.0 (wheel `cp39-abi3-win_amd64`). Other platforms not tested. |
| Sizes (bytes) | ML-KEM-768: public key 1184, secret key 2400, ciphertext 1088, shared secret 32. ML-DSA-65: public key 1952, secret key 4032, signature 3309. All match the FIPS 203/204 parameter tables (asserted in tests). |
| Abstraction | `backend/security/pqc.py` (`PqcBackend`); nothing else imports the library. |

## Conformance evidence

Test vectors: **NIST ACVP-Server** (`usnistgov/ACVP-Server`, commit `975de31eb83d87039ec88934fdc47d8c312b892d`), `gen-val/json-files/*/internalProjection.json`. `scripts/fetch_acvp_vectors.py` downloads them and copies the ML-KEM-768 and ML-DSA-65 cases **verbatim** into `tests/vectors/pqc/`; `MANIFEST.json` records the URLs and the SHA-256 of the full source files (ML-KEM: `a556952c…5b810f`, ML-DSA sigVer: `47cdd631…a55437`). No vectors were written or altered by us.

Results (`tests/pqc/test_conformance_acvp.py`, run through the `PqcBackend` interface):

| Check | Vectors | Result |
|---|---|---|
| ML-KEM-768 decapsulation (dk, c -> k) | 10 (ACVP "VAL": 5 valid, 5 modified-ciphertext / implicit rejection) | 10/10 match |
| ML-KEM-768 decapsulation of NIST ciphertexts from the encapsulation AFT group | 25 | 25/25 match |
| ML-KEM-768 encapsulation-key validity check | 10 (5 valid keys, 5 invalid: out-of-range coefficients) | library agrees with NIST on all |
| ML-KEM-768 decapsulation-key validity check | 10 (5 valid keys, 5 invalid: modified H) | library agrees with NIST on all |
| ML-DSA-65 signature verification (external, pure) | 15 (3 valid; 12 invalid: 3 modified message, 9 modified signature in the z / hint / commitment parts) | 15/15 agree |
| ML-KEM-768 generated keys follow the FIPS 203 layout (`dk = dkPKE‖ek‖SHA3-256(ek)‖z`) | 5 generated keys | pass |

Independent cross-check (`tests/pqc/test_interop_reference.py`): the pure-Python reference implementations `kyber-py` 1.2.0 (MIT OR Apache-2.0) and `dilithium-py` 1.4.0 (MIT) first pass the same NIST decapsulation/verification vectors, then interoperate with `pqcrypto` in both directions (encapsulate with one, decapsulate with the other; sign with one, verify with the other, including a context string). These two libraries are **test-only** and state they are not for production use. Behavioural tests (`test_mlkem768_mldsa65_behaviour.py`): valid round trips, modified/short/long/typed-wrong ciphertexts (malformed input raises `PqcError`; a corrupted but well-formed ciphertext yields a different secret, i.e. implicit rejection), wrong private key, 25 repeated independent KEM operations, signature verification failure on every single-byte message change, on signature corruption at 8 positions, on wrong public key, on malformed signature/key, context mismatch, and 15 independent signing keys.

**What this does and does not show.** It shows this library's *decapsulation, key-validity checking and signature verification* agree with NIST's known answers for ML-KEM-768 and ML-DSA-65, and that it interoperates with an independent implementation. **Not covered (not claimed):**
- **Key generation and signing KATs.** `pqcrypto.keygen()` and `sign()` take no seed/randomness input, so ACVP keyGen and sigGen answers cannot be reproduced. (Signing is randomised: two signatures over the same message differ, and both verify.)
- **Encapsulation KAT.** `encaps()` takes no `m` input; encapsulation is validated only indirectly (NIST's ciphertexts decapsulate correctly; our ciphertexts decapsulate correctly under an independent implementation).
- ML-DSA **pre-hash** (HashML-DSA) mode and the "internal" interface: not tested (our call with `hash_algorithm` raised `TypeError`); we do not use them.
- ML-KEM-512/1024 and ML-DSA-44/87: not tested.
- Side-channel/constant-time behaviour, fault resistance, RNG quality, memory hygiene: not assessed. No independent audit is known. **No FIPS 140 validation is claimed.**
- ACVP vectors passing is evidence of algorithm-level correctness, not a certification.

Reproduce: `python scripts/fetch_acvp_vectors.py` (needs internet), then `python -m pytest tests/pqc`.

## Key management

**Where keys live** (all under `keys/`, gitignored, verified by a test using `git check-ignore`):

| File | Contents | Protection |
|---|---|---|
| `keys/master.key` | 32-byte gateway master key (hex) | file permissions only (0600 on POSIX; folder ACL on Windows); or `QSHIELD_MASTER_KEY_HEX` |
| `keys/pqc/<id>.pub.json` | public key record (id, kind, algorithm, base64 key, SHA-256 fingerprint) | public |
| `keys/pqc/<id>.key.enc` | private key, AES-256-GCM sealed, associated data = kind/algorithm/id/fingerprint, random 96-bit nonce | encrypted under the key-encryption key below |
| `keys/pqc/<signer>.kek` | that signer's key-encryption key | plaintext file, permissions only; intended to be handed to the vision service *instead of* the master key |
| gateway DB `signers` table | signer public keys, authorised source and device list, status | integrity of the DB file only (public data) |

Key-encryption keys are HKDF-SHA256 subkeys of the master key with a per-purpose label (`pqc-kem:<id>`, `pqc-sig:<id>`), so the gateway can re-derive them and the vision service is given only its own. Private keys are decrypted into memory only, never logged, and on load a sign/verify or encapsulate/decapsulate self-test catches corrupt or mismatched files. Swapping a private-key file between ids, tampering with it, or swapping the public record fails to decrypt (AES-GCM associated data), all tested.

**Lifecycle / provisioning** (`scripts/pqc_provision.py`):
1. `init-gateway` creates `gateway-kem-1` (ML-KEM-768) and prints its fingerprint. Clients pin the public record (`keys/pqc/gateway-kem-1.pub.json`, copied out of band).
2. `enroll-signer vision-1 --device DEVICE-001` creates an ML-DSA-65 key, writes the sealed private key, the KEK file, and registers the public key in the gateway DB, scoped to one source (`usb_webcam`) and the listed devices. A signer can only report on its authorised devices.
3. The vision service runs with `--signer-id vision-1` (KEK from `keys/pqc/vision-1.kek` or `QSHIELD_SIGNER_KEK_HEX`).

**Rotation / replacement.** Ids are never overwritten. Rotate a signer by enrolling `vision-2`, switching the service, then `retire-signer vision-1` (or `--revoke` if compromised); the gateway rejects retired/revoked signers immediately. Rotate the gateway KEM key by `init-gateway --key-id gateway-kem-2`, re-pinning clients, listing both ids in `PQC_GATEWAY_KEM_KEY_IDS` (first is active) during the transition, then dropping the old one. There is no automatic expiry or rotation schedule.

**If the master key is lost.** Device HMAC credentials in the DB and the gateway KEM private key become unrecoverable, and the gateway can no longer re-derive signer KEKs. Recovery: create a new master key, `init-gateway` a new KEM key and re-pin clients, re-enroll devices (new HMAC secrets), and re-enroll signers. Already-issued signer KEK files still unseal their own keys, and public signer records in the DB stay valid, so signatures keep verifying (tested). If the master key is *stolen*, treat everything as compromised: revoke signers, rotate all keys, re-provision devices.

**Limits.** Same host, same OS account: anyone who can read `keys/` can decrypt everything. No HSM/TPM/OS keyring, no passphrase, no secure erase, keys live in process memory while running.

## Signed observation envelope (design **A**, the primary mechanism)

```json
{"protocol_version": 1, "algorithm": "ML-DSA-65", "signer_id": "vision-1", "source_id": "usb_webcam:0",
 "observation_id": "<uuid>", "timestamp": "<signing time, ISO-8601 UTC>",
 "payload": "<observation JSON as a string>", "signature": "<base64, 3309 bytes>"}
```
The signature covers `encode_fields("QSHIELD-SIGNED-OBSERVATION", [version, algorithm, signer_id, source_id, observation_id, timestamp, payload])` where `encode_fields` is a length-prefixed encoding (`u16 len‖domain‖u16 count‖(u32 len‖field)*`, `backend/protocol/canonical.py`), plus the ML-DSA context string `qshield/signed-observation/v1`. It never signs a JSON serialization: the payload is signed as the exact text transmitted, and is parsed only after verification. Shifting bytes between fields, changing any metadata field, or altering the payload invalidates the signature (tested, including a boundary-shift test).

Gateway checks, in order: protocol version -> algorithm -> signer enrolled and *active* -> signature -> timestamp within +/-`PQC_MAX_SKEW_S` (300 s) -> payload parses against the observation schema -> payload matches envelope (`observation_id`, source) -> signer authorised for that source and device -> device exists and is not revoked -> **replay** (`observation_id` already stored: `409`, event `pqc_observation_replay`). Every failure has its own reason code, stored as a security event; the HTTP response to the caller is generic (`401 authentication_failed`, `422`, `409`). The accepted envelope is stored with the observation so it can be re-verified later.

## ML-KEM session (design **B**, layered on A: the implementation is **C = both**, session optional)

`--secure` on the vision service establishes an ML-KEM-768 session and sends each signed envelope AES-256-GCM protected. Signed observations alone (A) already give authenticity and integrity; the session (B) adds confidentiality on the wire and transport-level replay protection. Details: `backend/security/session.py`.
- Client encapsulates to the **pinned** gateway public key; the init message (ciphertext, nonce, timestamp, ids) is ML-DSA-signed by the vision signer, so the gateway authenticates who is establishing the session and any tampering with the ciphertext is rejected *before* decapsulation.
- The gateway decapsulates and returns a server nonce, session id and a **key-confirmation tag** (HMAC-SHA256 over the transcript). A client that encapsulated to the wrong key, or whose ciphertext was corrupted (ML-KEM implicit rejection makes the gateway derive an unrelated secret), sees a bad confirmation and refuses to send.
- Keys: HKDF-SHA256(shared secret; salt = both nonces; info = label, session id, transcript hash) -> separate client->server, server->client and confirmation keys. Messages: AES-256-GCM, nonce = 0x00000000‖64-bit counter, AAD = session id‖direction‖counter, strictly increasing counters (replay/reorder rejected; counter advances only after authentication succeeds), 1-hour lifetime, max 64 concurrent sessions, handshake nonce replay cache.
- Composed from standard primitives, **not** TLS and **not externally reviewed**. Not provided: gateway signatures (gateway authenticity = possession of the pinned KEM key), session resumption, encrypted responses, forward secrecy against later compromise of the gateway's static KEM private key. Sessions are in-memory and lost on gateway restart (the sink re-establishes).

## Benchmarks (measured; `python scripts/bench_pqc.py`; raw data `docs/results/pqc-benchmark.json`)

Environment: 13th Gen Intel Core i7-13700HX (24 logical CPUs), Windows 11, Python 3.12.0, `pqcrypto` 1.0.0, single process, Python bindings, no CPU pinning, other processes running. 300 calls per round x 5 rounds per operation (1,500 samples; 60 x 5 = 300 for the handshake) after a 20-call warm-up; message signed/verified: a real 598-byte signing input built from a representative observation (`signed_message_bytes` in the JSON). **These are laptop numbers; they say nothing about ESP32 or other embedded performance.**

| Operation | median ms | mean ms | p95 ms | min ms | max ms |
|---|---|---|---|---|---|
| ML-KEM-768 keygen | 0.060 | 0.061 | 0.066 | 0.058 | 0.292 |
| ML-KEM-768 encapsulate | 0.069 | 0.073 | 0.076 | 0.068 | 0.888 |
| ML-KEM-768 decapsulate | 0.091 | 0.095 | 0.101 | 0.090 | 0.801 |
| ML-DSA-65 keygen | 0.232 | 0.240 | 0.259 | 0.227 | 1.183 |
| ML-DSA-65 sign | 9.424 | 9.413 | 10.146 | 8.706 | 12.814 |
| ML-DSA-65 verify | 0.188 | 0.204 | 0.323 | 0.186 | 0.754 |
| Full session handshake (client + server, in-process) | 10.013 | 10.060 | 10.798 | 9.293 | 11.380 |

Per-round medians differ by ~2% or less (see JSON). Sizes (bytes): KEM public key 1184, KEM secret key 2400, ciphertext 1088, shared secret 32; signature public key 1952, signature secret key 4032, signature 3309; a complete signed-observation envelope is ~5.2 kB of JSON (the signature is 4,412 base64 characters). ML-DSA signing being ~50x slower than verification is what this library does here; we did not investigate the cause. At the vision service's rates (observations emitted on state changes, well under one per second) signing costs are negligible.

## Tests (all pass; run `python -m pytest`)

`tests/pqc/` (conformance, interop, behaviour: 65 new), `tests/security/test_signed_observations.py`, `test_pqc_session.py`, `test_pqc_keystore.py`, `tests/integration/test_vision_signed_sink.py` (100 new, including the provisioning scripts and a gateway-startup path). Full suite: **347 passed**, of which the 182 pre-Phase-3 tests are unchanged. The signature-rejection tests were confirmed to fail when verification is sabotaged to always return true.

## Known limitations
- Library maturity, audit status and implementation source are as noted above; only KAT/interop-level evidence exists.
- Encapsulation, keygen and signing are not covered by known-answer vectors (library API).
- Single laptop trust domain: the gateway, its master key, the vision service's KEK and the DB share one host.
- Timestamps use the laptop clock for both sides; skew beyond 300 s breaks signed ingestion (fail closed).
- Replay detection for signed observations relies on the persistent `observation_id` uniqueness plus the freshness window; an attacker who can delay (not alter) a message within the window can still get a genuine, fresh observation delivered late.
- No DoS controls beyond size limits and a session cap; failed-verification events are not throttled.
- ESP32 remains HMAC-SHA256 only. Whether ML-DSA verification/ML-KEM decapsulation can run on the ESP32 is untested (research item R1).
