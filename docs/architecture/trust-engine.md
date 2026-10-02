# Trust Engine Specification

Status: **specification v1, implemented in Phase 4** (`backend/trust/`). Written before the code; the code and tests conform to this document, and any number below changes here first.
Provenance of the numbers: see **section 16**, which separates (A) previously established project parameters, (B) measured implementation results, (C) current prototype design parameters and (D) parameters that need empirical tuning. In short: the six factor **weights**, the **80 / 50 thresholds** and the *existence* of upward hysteresis come from `docs/technical-decisions.md` TD-08 (a project decision, itself labelled "a design choice, not empirically derived"); every other number, including the +5 hysteresis value, is a design choice made when this specification was written. **No parameter was optimised, calibrated or validated against data.** They are parameters (`backend/trust/config.py`), not constants buried in code.

Legend used in this document: **IMPLEMENTED** (code + tests exist), **DESIGNED** (specified, not built), **NEXT** (later phase).

## 0. Resolved gaps in the TD-08 outline
| Gap in the outline | Resolution in this specification |
|---|---|
| Six factors summing to 1 assumes every signal exists, but physical/sensor/integrity/network data mostly do not yet | Factors without evidence are **unavailable**; weights are renormalised over available factors; unavailable factors are listed in every record and never contribute credit (section 4.3) |
| "Penalties decay only while no new violation occurs" would still let trust drift back to 100 with time alone | Recovery is **gated on authenticated device evidence** and measured in *credited* time, not wall-clock time (section 6) |
| Factor `ai_confidence` mixed detector confidence with visual rule matches | Renamed `visual`; confidence is an *input to magnitude* (section 10), never a trust factor and never a substitute for authenticity |
| Anyone can send forged/replayed messages; unbounded penalties would let an attacker degrade a device's trust ("trust griefing") | Unauthenticated-origin events feed a **bounded pressure term** (section 4.5) that cannot alone cause quarantine |

## 1. Trust object
Trust is assigned to **the security state of one enrolled device identity** (e.g. `DEVICE-001`). Five concepts are kept separate and never merged:

| Concept | Meaning | Where it lives | Effect on device trust |
|---|---|---|---|
| Device identity / authentication | the device proved possession of its provisioned HMAC-SHA256 credential | `backend/security/auth.py` | an *input* (auth failures, replays) and a *gate* for what evidence is accepted |
| Vision-service identity | the software service proved possession of its ML-DSA-65 key | `backend/security/pqc_gateway.py` | determines the authenticity class of visual observations |
| Observation authenticity | this exact observation came, unaltered and fresh, from an enrolled signer | signed envelope verification | an *input*; establishes provenance only |
| Operator authentication | a human/dashboard holds the operator token | `backend/security/tokens.py` | **none**: operator/ingest authentication failures are **not** device-trust signals |
| **Device trust** | the engine's evaluation of the device's security state from all available signals | `backend/trust/` | the output |

## 2. Authenticity is not trust
- A valid ML-DSA signature proves **which key produced an observation** and that it was not altered. It does **not** prove the physical device is uncompromised or that the scene is benign.
- A valid HMAC tag proves **possession of the provisioned device secret**. It does not prove the device behaves correctly, that its sensors are truthful, or that its firmware is intact.
- Therefore: authentication is (a) a *precondition* for which evidence may be used at all (section 12), (b) a *negative* input when it fails, and (c) *never* a positive contribution to the score. A device that authenticates perfectly forever has the same maximum score (100) as a device that has never been observed misbehaving; valid signatures cannot raise trust above the baseline or offset a penalty.

## 3. Input signals
"Polarity": **N** = negative (reduces trust), **G** = gating (caps trust or limits which evidence is used), **E** = evidence of liveness (allows recovery, never adds trust). Authenticity classes: `DEVICE_HMAC`, `SIGNER_MLDSA`, `TOKEN_ONLY` (ingest bearer token, not PQC), `UNAUTHENTICATED` (any network party could produce it), `GATEWAY_LOCAL` (produced by the gateway from its own records).

| Signal (`SignalKind`) | Range / meaning | Source (today) | Required authenticity | Polarity | Available today |
|---|---|---|---|---|---|
| `device_evidence` | authenticated register / heartbeat / telemetry message received | HMAC-verified device endpoints | `DEVICE_HMAC` | E | yes (software device agent; ESP32 firmware unvalidated) |
| `physical_tamper` (level) | `tamper` boolean in telemetry; true = enclosure switch reports open | telemetry payload | `DEVICE_HMAC` | N + G | **schema field exists; only simulated (no hardware)** |
| `sensor_out_of_range` (level) | a telemetry field outside a *configured* limit | telemetry + `sensor_limits` config | `DEVICE_HMAC` | N | **unavailable unless limits are configured**; values simulated |
| `integrity_mismatch` (level) | self-reported `fw_version`/`cfg_hash` differs from a *configured* expectation | telemetry + expectation config | `DEVICE_HMAC` | N + G | **unavailable unless expectations are configured**; self-reported, not proof |
| `visual_rule_violation` (called `visual_anomaly` until Phase 4.1) | observation with `anomaly=true`, i.e. a detection that **matched a configured rule**; carries detector `confidence` in [0,1] | vision service observations | `SIGNER_MLDSA` (full weight) or `TOKEN_ONLY` (half weight) | N | yes (real webcam) |
| `camera_obstructed` / `camera_source_lost` | camera-health observation (`state` obstructed / source_lost) | vision service | `SIGNER_MLDSA` or `TOKEN_ONLY` | N | yes |
| `camera_frozen` / `camera_view_changed` (Phase 17) | camera-health observation (`state` frozen / view_changed): the same frame repeated (stuck or substituted feed); the scene no longer matches the reference view (camera turned, tilted, pointed elsewhere, or a large object placed in front) | vision service (`ai/vision/health.py`) | `SIGNER_MLDSA` or `TOKEN_ONLY` | N | yes (synthetic-frame tests; a static-scene check on a built-in laptop camera; not validated against staged physical tampering) |
| `camera_degraded` (Phase 17) | camera-health observation (`state` degraded): low light with the reference scene still visible, or blur | vision service | `SIGNER_MLDSA` or `TOKEN_ONLY` | N (small) | yes (as above) |
| `subject_proximity` (Phase 17) | visual observation with `anomaly_reason` `subject_too_close` or `rapid_approach`: **image-space heuristics** (a detected subject's bounding-box share of the frame, and its growth), not a distance | vision service (`ai/vision/proximity.py`) | `SIGNER_MLDSA` or `TOKEN_ONLY` | N (small) | yes (synthetic tests only) |
| `visual_clear` / `camera_ok` | non-anomalous observation / camera restored | vision service | `SIGNER_MLDSA` or `TOKEN_ONLY` | E (marks visual evidence available; `camera_ok` ends every camera episode) | yes |
| `invalid_tag`, `invalid_signature`, `auth_profile_mismatch` | authentication failure | gateway security events | `UNAUTHENTICATED` | N (pressure) | yes |
| `device_replay`, `observation_replay`, `handshake_replay` | counter/observation/nonce replay | gateway security events | `UNAUTHENTICATED` | N (pressure) + G (repeated) | yes |
| `stale_observation` | signed timestamp outside the freshness window | gateway | `UNAUTHENTICATED` | N (pressure, small) | yes |
| `auth_misbehavior` | valid signer sent metadata mismatching its payload, or reported on a device it is not authorised for | gateway | `SIGNER_MLDSA` | N + G | yes |
| `malformed_payload` | authenticated sender delivered a payload failing schema validation | gateway | `DEVICE_HMAC` or `SIGNER_MLDSA` | N | yes |
| `device_revoked` | device credential revoked | device record | `GATEWAY_LOCAL` | G (cap 0) | yes |
| `device_stale` (derived) | no authenticated device message for longer than the offline timeout | engine, from time | `GATEWAY_LOCAL` | N + G | yes |
| network behaviour anomalies (rate, topology, DNS ...) | - | - | - | - | **NOT AVAILABLE** (no data source); staleness is the only network-factor input |
| recovery state | RECOVERING / VERIFIED / RECOVERED | state machine | - | - | **representation only** (Phase 7 drives it) |
| Unknown signer / unknown device | attacker-chosen identity | gateway | `UNAUTHENTICATED` | recorded, **not attributed to any device** | yes (counted as unattributed) |

Explicitly **not** trust signals: `operator_auth_failed`, ingest-token failures, gateway-side faults (`credential_unreadable`, `credential_missing`, `auth_profile_not_implemented`), `too_many_sessions`. They concern the operator, the service or the gateway itself.

**Terminology (Phase 4.1): `visual_rule_violation`, not "anomaly".** The vision pipeline sets `anomaly=true` only when a detection matches a *configured rule* (for example a restricted object class inside a restricted zone; the `Observation` schema says "the `anomaly` flag only means the observation matched a configured rule"). It is a policy/rule match, **not** the output of an anomaly-detection model, and `confidence` is the detector's confidence in the underlying detection (e.g. that the object is really a "person"), **not** a probability that the device is compromised. The Phase 4 live run makes this concrete: its scratch rule treated chairs, cups and similar objects in a whole-frame restricted zone as violations. Only the trust-engine name changed; the observation schema field `anomaly`, the wire format and behaviour are unchanged. `docs/results/trust-live-run-phase4.json` is a record of the earlier run and still shows the old name `visual_anomaly`.

**Fail-closed input rule:** a signal that fails validation (malformed, confidence outside [0,1], non-finite or absurd timestamp, unknown device, unknown kind, or arriving with an authenticity class its kind does not permit) is **rejected**: it changes no score, and a diagnostic record with the reason is stored. It can never lower or *raise* trust silently.

## 4. Score
### 4.1 Factors and weights (from TD-08)
`identity_crypto` 0.25, `physical` 0.20, `config_integrity` 0.15, `sensor_consistency` 0.15, `visual` 0.15, `network` 0.10 (sum 1.00). **Design choice**, not empirically derived. Rationale: identity/cryptographic state gets the largest weight because everything else relies on it; physical is next because tampering defeats software controls; the remaining evidence classes are weaker or noisier and share the rest; network has the smallest weight because its only input today (liveness) is coarse.

### 4.2 Factor penalties
Each factor `i` carries a persistent penalty `p_i` in [0, 100] (0 = no adverse evidence, 100 = worst). Penalties only increase through signals (section 4.4) and only decrease through gated recovery (section 6). The `network` factor is not persistent: `p_network` is a pure function of time since the last authenticated device message (section 6.4).

### 4.3 Availability and the base score
A factor is *available* once evidence of its class has been received:
`identity_crypto`: from the first accepted signal of any kind for the device (a record may therefore start with an attributable violation, e.g. a forged-signature event attributed through a single-device signer, and then starts at `100 - pressure`); `network`: from the first authenticated device message; `physical`: after the first authenticated telemetry carrying `tamper`; `visual`: after the first authenticated observation of the device; `sensor_consistency`: only if `sensor_limits` are configured and telemetry carries those fields; `config_integrity`: only if expectations are configured and telemetry carries `fw_version`/`cfg_hash`.

With `A` the set of available factors and `W = Σ_{i∈A} w_i`:

```
raw = 100 − Σ_{i∈A} (w_i / W) · p_i
```

Unavailable factors are excluded, **never assumed healthy**: they are listed in every record (`unavailable`) and `coverage = W` is reported (1.00 = all six available). Consequence, stated plainly: with partial coverage the score reflects only the evidence that exists and a dashboard must show `coverage`.
A device with no authenticated evidence yet has **no trust record** (`NO_EVIDENCE`); the first authenticated message creates one at the baseline (`raw = 100`, TRUSTED). Baseline 100 is the maximum; it can never be exceeded.

### 4.4 Penalty magnitudes
Severity scale (factor points, applied to `p_i`; labels are only names for these numbers): `INFO 0`, `LOW 10`, `MEDIUM 30`, `HIGH 60`, `CRITICAL 100`. **Design choice**: roughly geometric so one CRITICAL saturates a factor while two HIGH do not.

| Signal | Factor | Points | Severity | Recovery half-life (credited s) | Notes |
|---|---|---|---|---|---|
| `physical_tamper` | physical | 100 | CRITICAL | 3600 | once per episode (level signal) |
| `sensor_out_of_range` | sensor_consistency | 60 | HIGH | 1800 | once per episode |
| `integrity_mismatch` | config_integrity | 60 | HIGH | 3600 | once per episode; self-reported |
| `visual_rule_violation` | visual | `100 · c^2 · m_auth` | CRITICAL x confidence | 900 | see section 10; per-episode maximum |
| `camera_obstructed` | visual | 60 | HIGH | 900 | per episode |
| `camera_source_lost` | visual | 30 | MEDIUM | 900 | per episode |
| `camera_frozen` | visual | 60 | HIGH | 900 | per episode; the camera no longer shows the live scene: as severe as an obstruction |
| `camera_view_changed` | visual | 60 | HIGH | 900 | per episode; the protected view is no longer watched: as severe as an obstruction |
| `camera_degraded` | visual | 30 | MEDIUM | 900 | per episode; evidence quality is reduced, which is not proof of interference: the severity of a lost source |
| `subject_proximity` | visual | `10 · m_auth` | LOW | 900 | per episode per reason; a heuristic; no impact below the confidence floor (0.30) |
| `auth_misbehavior` | identity_crypto | 60 | HIGH | 1800 | authenticated misbehaviour |
| `malformed_payload` | identity_crypto | 30 | MEDIUM | 1800 | authenticated sender |

Penalties from distinct signals add within a factor and are clamped at 100.

### 4.5 Unauthenticated pressure (anti-griefing term)
Events any network party can cause (forged tag/signature, replay, stale timestamp, profile downgrade attempts) do not add to a factor. They add to a single bounded **pressure** `q` in points of final score:

| Signal | Points |
|---|---|
| `invalid_tag`, `invalid_signature`, `auth_profile_mismatch` | 10 |
| `device_replay`, `observation_replay`, `handshake_replay` | 8 |
| `stale_observation` | 4 |

`q` is capped at **25** (design choice) and decays with half-life 600 credited seconds. The cap is the point: a flood of forged traffic can push a device to SUSPICIOUS (`100 − 25 = 75`) but **cannot by itself cause QUARANTINED** (needs `< 50`). Quarantine requires authenticated evidence.

### 4.6 Final score
```
uncapped = clamp( raw − q , 0 , 100 )
final    = min( uncapped , min over active caps )        (caps: section 5)
score    = round_half_up(final)                          integer in [0,100]
```
Deterministic: the score is a pure function of the ordered signal history, the configuration, and the evaluation time.

### 4.7 The complete scoring pipeline (normative; the code in `backend/trust/engine.py` implements exactly this)
This section is the single authoritative statement of how factor inputs become the published score. Sections 4.1-4.6 give the parts; this section gives the order and the arithmetic, and `tests/trust/test_spec_equation.py` checks it against an independent re-implementation and against the worked examples below.

**Step 1: factor penalties `p_i` in [0, 100]** (0 = no adverse evidence, 100 = worst; TD-08's factor score is `f_i = 100 − p_i`).
- *Persistent factors* (`identity_crypto`, `physical`, `config_integrity`, `sensor_consistency`, `visual`): `p_i` starts at 0 and only grows when a scored signal arrives (section 4.4). Contributions **add within a factor and the sum is clamped at 100**. Level signals (tamper, sensor, integrity) add once per episode; visual/camera signals add only the *increase* over the episode maximum already applied (section 6.3).
- *Visual magnitude:* `impact = 100 · c^2 · m_auth`; `m_auth = 1.0` for `SIGNER_MLDSA`, `0.5` for `TOKEN_ONLY`; `c < 0.30` gives impact 0. Camera obstructed / source lost add 60 / 30 times `m_auth`. Confidence changes only this magnitude.
- *Network factor:* not persistent. `p_network = 100 · clamp((a − 15)/(150 − 15), 0, 1)`, `a` = seconds since the last authenticated device message, evaluated at the evaluation time.
- A factor with no evidence of its class is **unavailable** (section 4.3); it has no `p_i`.

**Step 2: temporal decay** (recovery). Decay is applied **only when a clean, authenticated device message (`DEVICE_HMAC` evidence) arrives** and only for the credited time `Δc = clamp(t − max(t_prev_evidence, t_last_violation), 0, 45)`: every persistent penalty and the pressure term become `x ← x · 2^(−Δc / h)` (half-lives, section 4.4; pressure 600 s), values below 1e-9 become 0, and a factor whose own episode is still reported active (tamper, sensor, integrity) is skipped. Decay is not applied when a score is merely read, not with wall-clock time and not on out-of-order signals. `p_network` is the one time-derived value and is recomputed from `a` at every evaluation.

**Step 3: availability and renormalisation.** `A` = available factors, `W = Σ_{i∈A} w_i` (nominal weights, section 4.1). Effective weights are **renormalised over the available factors**: `w'_i = w_i / W`, so `Σ_{i∈A} w'_i = 1`. If `A` is empty there is no record (`NO_EVIDENCE`).

**Step 4: combining factors (weighted average of penalties).**
`raw = 100 − Σ_{i∈A} w'_i · p_i`  (equivalently `Σ w'_i · f_i`). Penalties from *different* factors combine **linearly** as a weighted average: nothing is multiplied and nothing is double counted; a factor at `p_i = 100` alone lowers `raw` by exactly `100 · w'_i` (at full coverage a lone tamper costs 20 points, which is why hard caps exist, section 5).

**Step 5: pressure.** `uncapped = clamp(raw − q, 0, 100)`. `q` (section 4.5, at most 25) is in **points of final score**: it is *not* weighted, not renormalised and not scaled by coverage.

**Step 6: caps and gates.** `final = min(uncapped, ceiling of every active cap)` (section 5). Caps are absolute ceilings, independent of weights and coverage. They are applied *after* pressure and *before* rounding.

**Step 7: bounds and rounding.** `raw` is a weighted average of values in [0, 100], so `0 ≤ raw ≤ 100`; `uncapped` is clamped to [0, 100]; caps only lower it; therefore `0 ≤ final ≤ 100`. `score = floor(final + 0.5)` (round half up), an integer in [0, 100]. The exact `final` is kept and published as `score_exact`.

**Step 8: state.** The state is derived from the integer `score` and the previous state (section 7).

**Coverage.** `coverage = W = Σ_{i∈A} w_i` in [0, 1] (0 when nothing is available). **Coverage is only reported** (`coverage`, `unavailable`, and `factors.*.available` in every record and API response). It is **not** a term in the score, there is no coverage floor and no coverage cap. Its only effect on the score is indirect, through the renormalisation `w'_i = w_i / W`.

**Security implications of "unavailable factors are excluded and available weights are renormalised" (intentional in Phase 4, TD-08 resolution 1: unavailable is neither healthy nor unhealthy):**
1. **A high score can occur with low coverage.** A device that has only sent authenticated messages (identity + network available, `coverage = 0.35`) has `score = 100`, TRUSTED. That score says "no adverse evidence *among the 35 % of the model that has data*", not "the device is healthy". Consumers (dashboard, Phase 6 policy) **must** show `coverage` and `unavailable` next to the score. No mitigation (for example refusing TRUSTED below a coverage level) is specified or implemented; that is an open design question for review, listed in section 16 (D).
2. **`identity_crypto` and `network` are "clean by default".** Once any evidence exists they are available with `p = 0`, so their combined nominal weight (0.35) dilutes the penalty of every other factor. Authentication itself is still never a *reward* (a score never exceeds 100 and valid signatures offset no penalty), but with these two factors always present the maximum damage of a single other factor is bounded by its renormalised weight.
3. **Penalties weigh more at low coverage** (example B below: the same visual violation gives 79 with four factors available and 85 with all six), and **a healthy factor appearing later raises the score** of a device that carries penalties (the `coverage_change` reason term reports this; example B). Hard caps exist so that severe conditions are not diluted this way.

**Worked examples** (default parameters; every number below is asserted in `tests/trust/test_spec_equation.py`).

| Ex. | Situation | Available (`W`) | Penalties `p` | Arithmetic | Result |
|---|---|---|---|---|---|
| **A** | all six factors available and clean | all (1.00) | all 0 | `raw = 100`, no pressure, no cap | `100`, TRUSTED, coverage 1.00 |
| **A2** | as A, then one signed rule violation, `c = 0.99` | all (1.00) | visual `100·0.99² = 98.01` | `100 − 0.15·98.01 = 85.2985` | `85`, TRUSTED |
| **B0** | only authenticated messages seen | identity, network (0.35) | 0, 0 | `raw = 100` | `100`, TRUSTED, **coverage 0.35** |
| **B** | identity, network, physical (clean tamper report) and visual; one signed violation, `c = 0.99` | 4 factors (0.70) | visual 98.01, others 0 | `w'_visual = 0.15/0.70 = 0.2143`; `100 − 0.2143·98.01 = 78.9979` | `79`, **SUSPICIOUS** (the same observation scores 85 in A2) |
| **B2** | identity, network, visual only; `c = 0.99` | 3 factors (0.50) | visual 98.01 | `100 − (0.15/0.50)·98.01 = 70.597` | `71`, SUSPICIOUS |
| **C1** | identity, network, physical; tamper reported active | 3 factors (0.55) | physical 100 | `raw = 100 − (0.20/0.55)·100 = 63.6364`; cap `physical_tamper` = 55 | `final = min(63.6364, 55) = 55`, SUSPICIOUS (the cap, not the weights, decides) |
| **C2** | as B with `c = 0.9` (`p_visual = 100·0.81 = 81`), then tamper active within 60 s (`p_physical = 100`), then a forged HMAC tag (`q = 10`); last evidence 15 s ago (`p_network = 0`) | identity, network, physical, visual (0.70) | phys 100, vis 81, id 0, net 0 | `w'_phys = 0.2857`, `w'_vis = 0.2143`; `raw = 100 − 28.5714 − 17.3571 = 54.0714`; `uncapped = 54.0714 − 10 = 44.0714`; caps: `confirmed_incident` 30, `physical_tamper` 55 | `final = min(44.0714, 30, 55) = 30`, **QUARANTINED** |
| **D** | token-only observation, `c = 0.9` (compare with C2's visual) | as B | visual `100·0.81·0.5 = 40.5` | half the signed impact; cannot confirm an incident | penalty 40.5 |
| **E** | decay: physical penalty 100, tamper cleared, 80 clean messages each crediting 45 s | physical | 100 → `100·2^(−3600/3600)` | `= 50` after 3600 credited s | 50.0 (half-life 3600 s) |

Example C2 in words: the weighted sum alone would give 44 (already QUARANTINED range); the confirmed-incident cap lowers it to 30. In C1 the weighted sum (63.6) would leave the device TRUSTED-adjacent, and the cap forces 55. Removing the pressure term (no forged tag) would give `uncapped = 54.07`, still capped to 30.

## 5. Caps and gates
A cap is a ceiling on `final` regardless of the weighted sum. `final = min` of all active caps. Hold times are measured in **credited seconds** (section 6): they cannot expire while the device is silent.

| Cap (`name`) | Value | Condition | Release |
|---|---|---|---|
| `revoked_device` | 0 | device credential revoked | never automatic (re-enrolment) |
| `confirmed_incident` | 30 | tamper **plus** at least one other modality within the correlation window (section 9) | 1800 credited s after last contributing signal |
| `physical_tamper` | 55 | tamper reported (unconfirmed) | tamper cleared **and** 900 credited s |
| `correlated_incident` | 55 | two modalities without tamper | 900 credited s |
| `repeated_replay` | 65 | 3 or more replay events in 600 s | 900 credited s |
| `integrity_mismatch` | 65 | latest self-reported integrity value mismatches the configured expectation | next matching report |
| `auth_violation` | 70 | `auth_misbehavior` from a valid signer | 900 credited s |
| `stale_device` | 79 | no authenticated device message for more than 45 s (3 x offline timeout) | next authenticated device message |

Design choices, with rationale: 30 sits below the quarantine threshold, so a *confirmed* cyber-physical incident quarantines regardless of weights; 55 keeps single-modality or unconfirmed physical evidence inside SUSPICIOUS (a self-reported tamper switch is not proof); 65-70 keep repeated-but-unauthenticated or self-reported conditions out of TRUSTED without quarantining; 79 means "cannot be TRUSTED without fresh authenticated evidence".

## 6. Temporal behaviour
### 6.1 Credited time
Wall-clock time never heals a device. Recovery uses **credited seconds**: each *clean* authenticated device message at time `t` credits
`Δc = clamp( t − max(t_prev_evidence, t_last_violation), 0, credit_cap )`, with `credit_cap = 45 s` (3 x offline timeout). Long silences are not banked; intervals containing a violation are not credited (TD-08: recovery only while no new violation occurs). Only `DEVICE_HMAC` evidence credits time (a live vision service does not attest device health).

### 6.2 Recovery (decay) formula
For every persistent penalty `x` in {`p_i`, `q`} with half-life `h`:
`x ← x · 2^( −Δc / h )`. Half-lives in section 4.4 (pressure 600 s). This is a decay **toward** 0 but never a jump: e.g. a saturated physical penalty (100) with `h = 3600` credited seconds falls to 50 after one hour of *healthy, authenticated* reporting. Silence (or an attacker stopping) credits nothing: trust does not return.

**Active episodes do not heal.** While a tamper, sensor-out-of-range or integrity-mismatch condition is *still reported active*, the penalty of its own factor is not decayed (other factors and pressure still decay). An attacker who keeps the condition true therefore cannot wait it out; decay begins only after the device reports the condition cleared.

### 6.3 Holds, episodes and duplicates
- **Level signals** (tamper, sensor, integrity) are episodes: the penalty is applied once when the condition becomes true; repeated identical reports only refresh the hold. The condition clearing ends the episode; a new episode applies a new penalty.
- **Visual/camera episodes**: observations of the same `(kind, zone, object)` within 30 s form one episode; the episode's applied penalty is the **maximum** impact seen (only the increase over what was already applied is added), so a vision service repeating an anomaly every 5 s is not counted repeatedly. Camera-health kinds form one episode per kind, proximity one per reason; `camera_ok` ends every camera episode, so a camera that is covered again after it was restored is a new episode and is penalised again.
- **Duplicates**: a signal id seen before is ignored (no penalty, counted). The id is derived from the gateway record (`event:<id>`, `obs:<observation_id>`, `msg:<id>`), so re-processing cannot double count.
- **Discrete violations** (replays, invalid signatures) each count, but only through the bounded pressure term or a factor clamp.

### 6.4 Freshness and staleness
- **Observation freshness**: an observation whose `observed_at` differs from gateway receipt by more than 300 s is *not scored*; a `stale_observation` record with impact 0 is kept. (The signed path already rejects such envelopes; this protects the token-only path.)
- **Device staleness** (derived, not event-sourced): with `a` = seconds since the last authenticated device message and `T = 15 s` offline timeout: `p_network = 0` for `a ≤ T`, rising linearly to 100 at `a = 150 s`, `p_network = 100 · clamp((a − T)/(150 − T), 0, 1)`. It vanishes when a fresh authenticated message arrives (liveness is not a persistent penalty). The `stale_device` cap (section 5) applies for `a > 45 s`.
- **Out-of-order signals** are processed at the latest known time and flagged; they earn no time credit.
- **Definition (Phase 11 correction):** a signal is *out of order* only if its receipt time is older than a signal already applied (`last_signal_ts`). A time-driven evaluation (staleness check) that ran between a record's receipt and its processing, for example an enforcement check or a dashboard poll, does not make it out of order: it is processed at the engine's current time (published time never moves backwards) and is credited from its own receipt time. Found in the live integrated demo: with a real clock the previous rule silently denied recovery credit to legitimate messages (tests use a frozen clock and could not see it). Regression tests in `tests/trust/test_engine_scoring.py`.

## 7. State machine
States: `TRUSTED`, `SUSPICIOUS`, `QUARANTINED`, `RECOVERING`, `VERIFIED`, `RECOVERED`.

Score thresholds (TD-08; on the integer `score`): `TRUSTED ≥ 80`; `SUSPICIOUS 50-79`; `QUARANTINED < 50`. Hysteresis: SUSPICIOUS -> TRUSTED needs `score ≥ 85` (design choice, +5). Revocation forces QUARANTINED immediately.

Legal transitions (everything else is **rejected**, never silently accepted):

| From | To | Trigger | Required evidence | Phase 4 |
|---|---|---|---|---|
| (first evidence) | TRUSTED | first authenticated message, score ≥ 80 | evidence id | **IMPLEMENTED** (automatic) |
| TRUSTED | SUSPICIOUS | `score < 80` | trust change reasons | **IMPLEMENTED** (automatic) |
| SUSPICIOUS | TRUSTED | `score ≥ 85` | trust change reasons | **IMPLEMENTED** (automatic) |
| TRUSTED / SUSPICIOUS | QUARANTINED | `score < 50`, or revoked | trust change reasons | **IMPLEMENTED** as a *recorded state* and recommendation only |
| QUARANTINED | RECOVERING | operator/recovery orchestrator request | reason + evidence id; device not revoked | transition **validated**; driven by Phase 7 (**NEXT**); no score requirement |
| RECOVERING | VERIFIED / QUARANTINED | health checks pass / fail (or automatic on a fresh authenticated fault report) | check results | validated; VERIFIED requested by Phase 7 (**NEXT**), QUARANTINED also **IMPLEMENTED** automatically (section 7.1) |
| VERIFIED | RECOVERED / QUARANTINED | trust ramp completes (**score ≥ 50**) / regresses | ramp record | validated with a score guard; **NEXT** |
| RECOVERED | TRUSTED / SUSPICIOUS / QUARANTINED | rebuilt trust: TRUSTED needs **score ≥ 85**, SUSPICIOUS needs **score ≥ 50**, QUARANTINED always | score + record | validated with score guards; **NEXT** |
| RECOVERING / VERIFIED | QUARANTINED | revoked, or a fresh **authenticated** fault report, or an explicit failed check | trust change reasons | **IMPLEMENTED** (automatic; **not** on score alone, section 7.1) |
| RECOVERED | QUARANTINED | `score < 50` or revoked | trust change reasons | **IMPLEMENTED** (automatic) |

Additional rules: QUARANTINED is **sticky**: a rising score never leaves it (TD-10: a reboot or silence is not recovery); only an explicit, validated `request_transition` can. **Phase 4 enforces nothing**: no session revocation, no blocked endpoints, no automatic recovery; the state and the recommended action are *recorded* (QUARANTINE automation is Phase 6, recovery Phase 7).

### 7.1 Recovery-state semantics (Phase 4.1; Phase 7 will drive the transitions, Phase 4 only records and validates them)
**Why this was changed.** Phase 4 originally dropped RECOVERING/VERIFIED back to QUARANTINED whenever the score was below 50. But a device that has just been remediated still carries its decaying penalties and holds (section 6: half-lives up to 3600 credited s, holds up to 1800), so its score is *necessarily* below 50 when recovery starts, and the score can only rise through fresh authenticated evidence gathered *while* recovering. The old rule would have made RECOVERING unsustainable and blocked Phase 7 from ever remediating. The rule is now: **recovery states are held by evidence of failure, not by the score alone.**

Rules (all in `backend/trust/state_machine.py` / `engine.py`, tested in `tests/trust/test_recovery_semantics.py`):
1. **Entry** to RECOVERING is only an explicit, validated request (reason + evidence id) from QUARANTINED, and never for a revoked device (revocation needs re-enrolment). No score requirement.
2. **RECOVERING and VERIFIED hold regardless of score.** They return to QUARANTINED automatically only on (a) revocation, or (b) a fresh **authenticated** report that a fault is present: tamper active, sensor out of range, integrity mismatch, `auth_misbehavior`, `malformed_payload`, or a signed (`SIGNER_MLDSA`) rule violation / camera obstruction / source loss / frozen feed / changed view (Phase 17). A degraded image or a proximity heuristic is not a fault report: neither says the remediation failed. Unauthenticated pressure and token-only observations can never trigger it (they must not be able to knock a device out of recovery). An explicit failed-check request (`→ QUARANTINED`) is always allowed.
3. **Fresh authenticated evidence keeps crediting time in every state**, including QUARANTINED and RECOVERING (`credit_clock`, decay of penalties and pressure). The score therefore ramps up without changing the state; in QUARANTINED it can reach 100 and the state still stays QUARANTINED (sticky).
4. **VERIFIED → RECOVERED needs `score ≥ 50`** (dynamic trust must have left the quarantine range). **RECOVERED → TRUSTED needs `score ≥ 85`** (the hysteresis re-entry value); **RECOVERED → SUSPICIOUS needs `score ≥ 50`**. Otherwise the request is rejected with `IllegalTransition` and the state is unchanged. RECOVERED is never promoted automatically; it falls back to QUARANTINED automatically if the score drops below 50.
5. The engine has **no recovery timeout** and never resets or forgives a penalty on request: there is no API to clear penalties. Only credited authenticated evidence lowers them.

| Situation | Behaviour |
|---|---|
| RECOVERING with score < 50 | Holds. Clean evidence credits time and the score rises; nothing else changes. (A Phase 4 change: it used to regress.) |
| Remediation succeeds | The orchestrator requests VERIFIED (health checks, reason + evidence id; the engine does not judge the checks). The device must keep sending clean authenticated evidence; the ramp proceeds by credited time. RECOVERED at `score ≥ 50`, then TRUSTED at `≥ 85` (or SUSPICIOUS at `≥ 50`). |
| Remediation fails | An authenticated fault report (rule 2) sends RECOVERING/VERIFIED back to QUARANTINED automatically, with a recorded reason; the orchestrator can also request it explicitly. |
| Fresh evidence unavailable (device silent) | State holds; nothing is credited, the score never rises (network staleness only lowers it). The engine will not time out by itself: **Phase 7 must own a recovery deadline** and request `→ QUARANTINED` with reason and evidence id. Holding is not a grant of access: access policy for these states is Phase 6/TD-10 (RECOVERING = recovery-protocol messages only). |
| Verification succeeds but dynamic trust is below threshold | VERIFIED holds while the ramp accumulates; RECOVERED is refused below 50, TRUSTED refused below 85. The device is never returned to TRUSTED on a health-check result alone. |
| Revoked device | Only QUARANTINED is reachable; automatic return on revocation. |

**Interface requirements for Phases 6-7 (not implemented; recorded so they are not missed):**
- Quarantine enforcement must still **record authenticated messages from a quarantined or recovering device as evidence** (the `device_messages` stream / `device_evidence`). If those messages are dropped, no credited time accrues and the score can never rise, which would make recovery impossible. Recovery-channel messages must carry the device credential (or its re-provisioned successor).
- Remediation only *starts* a ramp; trust is restored by fresh authenticated evidence. At the default parameters this is slow. Measured in a simulation with clean messages every 20 s after a tamper + sensor + integrity incident was cleared (confirmed-incident cap and penalties from that incident): score ≥ 50 after about 31 minutes, ≥ 80 after about 57 minutes, ≥ 85 after about 78 minutes. This duration is a direct consequence of category C/D parameters (section 16) and is likely to need tuning before a demonstration.
- The orchestrator that calls `TrustService.request_transition` needs its own authentication and audit trail; the service has no HTTP write endpoint.

## 8. Event severity mapping
Numeric, not label-only: section 4.4 (factor points), 4.5 (pressure points), section 5 (caps). A label is a display name for its number: `INFO 0`, `LOW 10`, `MEDIUM 30`, `HIGH 60`, `CRITICAL 100`.

## 9. Multi-signal fusion
Modalities: `PHYSICAL` (tamper report, `DEVICE_HMAC`), `VISUAL` (anomaly with `c ≥ 0.5`, **`SIGNER_MLDSA` only**), `SENSOR` (out-of-range, `DEVICE_HMAC`). A token-only visual anomaly still scores (half weight) but **cannot confirm** an incident.
A level modality (`PHYSICAL`, `SENSOR`) is *present* while its episode is active **or** within the window after its last report; the event modality (`VISUAL`) is present within the window after its last qualifying anomaly. Within a correlation window of **60 s** of event time:
- one modality: no incident; the signal's own penalty and cap apply;
- two modalities without tamper: **`correlated_incident`** (cap 55);
- tamper plus any other modality: **`confirmed_incident`** (cap 30).
The incident is a *record* (`incident_id`, class, member signal ids) attached to the trust change. It adds **no extra penalty**: each modality penalises its own distinct factor once (a person, a tamper report and a vibration excursion are three different underlying observations, not one counted three times); the incident only imposes the cap. The same observation never counts as two modalities.

**The camera as part of the security boundary (Phase 17).** A **signed** (`SIGNER_MLDSA`) report that the camera is `obstructed`, `frozen` or its view `view_changed` also makes the `VISUAL` modality present: the camera's view of the protected area has been interfered with, which is visual evidence in the same sense as a rule match. No new class, cap or threshold is introduced; the rules above apply unchanged, so:
- camera interference alone: its visual penalty only (60 points on the visual factor, about 9 points of score with full coverage): **never an incident, never quarantine**;
- tamper plus camera interference within 60 s (someone blinds or turns the camera and opens the enclosure): **`confirmed_incident`** (cap 30, QUARANTINED), exactly as tamper plus a signed rule violation;
- sensor excursion plus camera interference: **`correlated_incident`** (cap 55);
- camera interference plus a rule violation: still **one** modality (the same camera, the same signer), so a compromised vision key alone still cannot open an incident.
**Not** modality evidence: `source_lost` (indistinguishable from a USB or driver fault), `degraded` (lighting or focus), the proximity heuristics, and any token-only report. They keep their own small penalties.

## 10. Confidence
`visual_rule_violation` impact = `100 · c^2 · m_auth`, `c` = detector confidence, `m_auth` = 1.0 for `SIGNER_MLDSA`, 0.5 for `TOKEN_ONLY`. Detections with `c < 0.30` (floor, design choice) are recorded with impact 0. Examples: `c = 0.51` -> 26; `c = 0.99` -> 98 (factor points). Confidence scales the **magnitude** only: it can neither create trust nor bypass authenticity (an unauthenticated source cannot deliver a visual anomaly at all; section 12), and a high-confidence but token-only observation counts at half weight and never confirms an incident. `c` outside [0,1] or non-finite is rejected.

## 11. Explainability
Every state or score change produces one **`TrustChange`** record:
```json
{ "event_id": "TC-DEVICE-001-7", "device_id": "DEVICE-001", "timestamp": 1790000000.12,
  "previous_score": 100, "new_score": 71, "delta": -29, "previous_exact": 100.0, "new_exact": 70.7,
  "previous_state": "TRUSTED", "new_state": "SUSPICIOUS",
  "trigger_signals": ["obs:ab12..."],
  "reasons": [ {"signal": "visual_rule_violation", "factor": "visual", "impact": -29.3, "confidence": 0.99, "authenticity": "SIGNER_MLDSA", "source_ref": "obs:ab12..."} ],
  "caps_active": [], "incident": null, "coverage": 0.5, "unavailable": ["physical", "config_integrity", "sensor_consistency"] }
```
**Exact attribution:** `Σ reasons.impact == new_exact − previous_exact` (tested to 1e-9). Reason terms: per-factor terms using the post-update weights (`−w'_i · Δp_i`, split into the triggering signal and `healthy_evidence_recovery`), `network_liveness`, the pressure delta, a `coverage_change` term (`−Σ(w'_i − w_i)·p_i`) when availability changes, a `bounds` term for clamping, and `cap:<name>` for cap effects. Nothing is left unexplained; reasons are ordered by magnitude.
`GET /api/v1/trust/{device}` returns the current score, factor penalties, weights, coverage, unavailable factors, active caps, pressure, provenance notes (e.g. `physical: simulated by software-agent`) and recent changes.

**Event emission rule (IMPLEMENTED).** The exact score and all penalties are updated on every signal, but a `TrustChange` event is persisted only when the published integer score, the state, the active-cap set or an incident changes, or when the triggering signal is itself a scored signal with a non-zero effect. Routine clean heartbeats that merely decay a penalty by a fraction of a point do not create events (a live run otherwise produced one zero-delta event per heartbeat). Because the exact value is carried forward, every emitted event still sums exactly to its exact delta.

## 12. Security boundaries
| Signal | Authenticated by | Provenance class |
|---|---|---|
| tamper, sensor values, fw/cfg hash | device HMAC (message integrity + credential possession) | **self-reported by the device**; a compromised device can lie; firmware/config hashes are evidence, **not proof** of integrity |
| visual anomaly, camera health | ML-DSA signature of the vision service (or ingest token) | **inferred by AI**; authenticity says who produced it, not that the detector is right |
| camera interference (frozen, view changed, degraded), proximity | ML-DSA signature of the vision service (or ingest token) | **inferred from image statistics and image-space heuristics** (`ai/vision/health.py`, `ai/vision/proximity.py`); no distance is measured; thresholds unvalidated |
| invalid tag/signature, replay, staleness | none (that is the point) | **locally generated** by the gateway from rejected input; attacker-influenceable, hence the pressure bound |
| revoked, staleness cap | gateway records/clock | **configuration/locally derived** |
| sensor limits, integrity expectations | operator configuration | **configuration-derived** (no digital twin yet) |
Enforcement: each signal kind lists the authenticity classes it may arrive with (`REQUIRED_AUTH`); anything else is rejected. A visual anomaly can never arrive as `UNAUTHENTICATED`; device evidence can never arrive as `TOKEN_ONLY`.

## 13. Threat model (what the engine does and does not do)
Evaluates trust from **available signals**. It does not detect every compromise, prevent attacks, guarantee security, prove firmware integrity or make anything quantum-safe.

| Threat | Handling / limitation |
|---|---|
| Stolen device HMAC secret | attacker can send authenticated, plausible telemetry and **evade** the engine; only replay/counter anomalies or contradicting visual/sensor evidence would show |
| Malicious telemetry from a compromised device | tamper/sensor lies are self-reported: **evade**; configured limits catch only crude out-of-range values |
| Forged observations | rejected at the gateway; the attempts feed bounded pressure |
| Replay | pressure + `repeated_replay` cap |
| Delayed genuine observation | within 300 s: scored normally (freshness window); beyond: not scored |
| Compromised vision service | can sign false anomalies (raise penalties: trust griefing) or suppress them (**evade**); scope-limited, revocable signer |
| Compromised gateway host | out of scope; engine and evidence are on the compromised host |
| Sensor spoofing | undetectable without physical cross-checks; only configured limits and cross-modal correlation help |
| Physical tampering | only if the device reports it; a tamper that also disables reporting is invisible except via staleness |
| Camera blinded, turned, frozen or replaced (Phase 17) | reported by the vision service from image statistics, signed; penalised alone, and confirms an incident together with a tamper report; an attacker who changes the view slowly enough to stay under the thresholds, or before the reference view is learned, is not detected |
| Trust griefing by network attacker | bounded to `q ≤ 25` -> SUSPICIOUS at worst, never QUARANTINED |
| AI false positives/negatives | unmeasured; false positives lower trust (bounded by confidence and episodes); false negatives leave trust unchanged |
| Silent attacker | staleness lowers network factor and caps at 79; no recovery without authenticated evidence |
An attacker who controls a device credential *and* keeps sending healthy-looking evidence still evades the engine: this is a limitation of the available signals, not of the arithmetic.

## 14. Acceptance criteria (each is a test in `tests/trust/`)
Baseline trusted device; single low-severity anomaly; high-confidence and low-confidence visual anomaly (0.51 < 0.99); physical tamper (cap 55); confirmed incident (cap 30, quarantine); invalid HMAC; invalid signature; unknown signer/device (unattributed, no score change); replay and repeated replay (cap 65); revoked device (score 0, QUARANTINED); multiple simultaneous signals without double counting; trust decay per the formula; no recovery without evidence; staleness; state hysteresis; sticky QUARANTINED; invalid transitions rejected; duplicate events ignored; stale/future observations; valid authenticated observation with anomalous content; token-only weaker than signed; unauthenticated source cannot deliver visual/tamper signals; determinism; bounds [0,100]; every non-zero delta explained; malformed/NaN/negative-confidence inputs rejected with a diagnostic; flood bounded by pressure cap.

## 15. Implementation status

**IMPLEMENTED (Phase 4)** - code, tests (`tests/trust/`) and the live run in `docs/results/trust-live-run-phase4.json`:
- `backend/trust/model.py` signal model, authenticity classes and boundary table (`REQUIRED_AUTH`), validation (fail closed), `TrustChange`/`Reason`.
- `backend/trust/config.py` all parameters of this document; a config file may only supply configuration-derived expectations (`sensor_limits`, `expected_fw_version`, `expected_cfg_hash`, `offline_timeout_s`), never weights, caps or thresholds.
- `backend/trust/engine.py` deterministic pure-logic engine: availability/coverage, factor penalties, bounded pressure, caps and holds, credited-time decay, staleness, episodes, duplicates, fusion incidents, exact attribution, state transitions.
- `backend/trust/state_machine.py` legal-transition table, hysteresis, sticky QUARANTINED, `request_transition` validation (reason + evidence id required, score guards, revoked devices cannot leave QUARANTINED).
- `backend/trust/adapters.py` feature extraction: gateway records to signals; the authenticity class is derived from *how the gateway authenticated the record*, never from record content.
- `backend/trust/service.py` pull-based service over `security_events`, `observations`, `device_messages` with persisted cursors; persists trust events, per-device state and diagnostics.
- Gateway: trust middleware (runs after every POST; a trust fault records a `trust_engine_error` event and never changes the response), operator-only `GET /api/v1/trust`, `/api/v1/trust/{id}`, `/api/v1/trust/{id}/history`, `/api/v1/trust/diagnostics`. No trust write API exists.

**Inputs that really exist today** and are wired: authenticated device messages (liveness), telemetry `tamper` (device-reported; simulated by the software agent so far), signed and token-only visual observations with detector confidence, camera health, gateway authentication failures (invalid tag/signature, replays, stale timestamps, profile mismatch), signer-authorisation violations, revocation. **Conditionally available** (configuration only): sensor range limits, expected firmware version / config hash. **Unavailable and reported as such:** anything from a real ESP32 sensor set, hardware tamper switches, firmware attestation, network-behaviour analytics, digital-twin expectations.

**Spec/code refinements found while implementing** (folded into the text above): active episodes block their own factor's decay; a record starts at the first accepted signal; only material changes emit events. Phase 4.1 corrections: the exact pipeline is now normative (section 4.7); `RECOVERING`/`VERIFIED` no longer regress on a low score alone (section 7.1); explicit transitions have score guards; the signal `visual_anomaly` was renamed `visual_rule_violation` (terminology only).

**Measured cost** (`scripts/bench_trust.py`, `docs/results/trust_bench.json`; one Windows laptop, single device, in-memory SQLite): `TrustEngine.apply` about 53 us mean / 73 us p99; `process_pending` after one new gateway record about 0.7 ms mean / 1.3 ms p99; batch throughput about 6.7k records/s. These are processing costs of this code on one machine, not end-to-end detection latency and not a real-time guarantee.

**IMPLEMENTED (Phase 17): the camera as part of the security boundary.** New signal kinds `camera_frozen`, `camera_view_changed`, `camera_degraded` and `subject_proximity` (section 3), their penalties (section 4.4), camera interference as `VISUAL` modality evidence (section 9) and as a recovery fault (section 7.1). Tests: `tests/trust/test_camera_boundary.py` (engine) and `tests/ai/test_camera_security.py` (the vision side).

**DESIGNED, NOT IMPLEMENTED:** digital-twin-derived expectations, evidence-chain anchoring of trust events (Phase 8), network-behaviour signals, per-source rate limiting in front of the gateway, multi-process/multi-gateway coordination (the service assumes one process owns the DB).

**NEXT:** attack-simulation suite (Phase 5), quarantine enforcement (session revocation, blocked endpoints; Phase 6), recovery orchestration and trust ramp (Phase 7), dashboard (Phase 10), real ESP32 tamper/sensor signals.

**What an attacker can still do (not prevented):** (1) with a stolen device HMAC secret, report clean telemetry and stay TRUSTED: the engine trusts authenticated device self-reports, and tamper/integrity fields are self-reported, not attested; (2) an attacker who avoids or suppresses the configured visual rules is invisible to the visual factor; (3) a network attacker who can replay or forge traffic aimed at a device or its signer can drive it to SUSPICIOUS (never QUARANTINED) through the pressure term: a bounded trust-denial we accept instead of letting unauthenticated input quarantine devices (the live run showed exactly this: 91 to 73 after one forged and one replayed observation); (4) a compromised vision-service key can inject authenticated false anomalies (bounded: quarantine needs tamper evidence or repeated violations from other modalities) or withhold real ones; (5) the gateway host is trusted: its DB, keys and clock are not protected by this engine; (6) sensor and integrity coverage is only as good as the configured limits; (7) the ESP32 path is HMAC, not post-quantum, and no signal here proves firmware integrity.

## 16. Parameter provenance and evidence (Phase 4.1)
Purpose: keep four things apart so that no number is mistaken for evidence. **Nothing in this repository shows that any weight, threshold, half-life, floor, cap or point value was optimised, calibrated or validated**: there is no incident dataset, no false-positive/false-negative study, no ROC analysis, no user study, and no tuning against the demo (TD-08: "No numbers are tuned to make a slide"). The values are kept unchanged from Phase 4.

**A. Previously established project parameters** (decisions recorded before Phase 4; *established in the project*, none is externally validated science):

| Parameter | Value | Source |
|---|---|---|
| factor weights | 0.25 / 0.20 / 0.15 / 0.15 / 0.15 / 0.10 | TD-08, itself "a design choice, not empirically derived"; `ai_confidence` was renamed `visual` in Phase 4 (same weight) |
| state thresholds | TRUSTED ≥ 80, SUSPICIOUS 50-79, QUARANTINED < 50 | TD-08 (configurable there) |
| upward hysteresis | exists; the value **+5 (85) is a Phase 4 choice** (TD-08 gave no number) | TD-08 (existence only) |
| device offline timeout | 15 s | Phase 1 gateway setting `DEVICE_OFFLINE_TIMEOUT_S` |
| observation freshness / clock-skew window | 300 s | Phase 3 protocol setting `PQC_MAX_SKEW_S` |
| state names and order | TRUSTED, SUSPICIOUS, QUARANTINED, RECOVERING, VERIFIED, RECOVERED | TD-10 |
| authenticity primitives | HMAC-SHA256 (device), ML-DSA-65 / ML-KEM-768 (vision service) | TD-18 / NIST FIPS 203, 204 via reviewed libraries; relevant to *authenticity*, not to any trust parameter |
There is **no externally grounded numeric trust parameter** in this specification.

**B. Measured implementation results** (facts about this code on this machine, not evidence that the parameters are right):
- Trust-engine cost: `docs/results/trust_bench.json` (about 53 µs mean per `apply`, about 0.7 ms per gateway record end to end; one laptop, one device, not a real-time claim).
- Phase 4 live run: `docs/results/trust-live-run-phase4.json` (three real detections at detector confidences 0.46 / 0.57 / 0.66 moved the score 100 → 95 → 93 → 91; one forged and one replayed observation moved it to 73). One session, one scene, one scratch rule: an illustration of the mechanism, not a calibration.
- Test results (`tests/trust/`) and the simulated recovery ramp in section 7.1 (a property of the parameters, not a validation of them).
- Phase 3 PQC benchmark (`docs/results/pqc-benchmark.json`): cost of the cryptography only.

**C. Current prototype design parameters** (author's choices with a stated rationale; all in `backend/trust/config.py`; none validated):
severity scale 0/10/30/60/100 (roughly geometric); per-signal points (section 4.4); visual impact `100·c²` with exponent 2, floor 0.30, token-only multiplier 0.5, correlation minimum confidence 0.5; pressure points 10/8/4, pressure cap 25 (chosen so `100 − 25 = 75 ≥ 50`), pressure half-life 600 s; cap ceilings 0/30/55/55/65/65/70/79 and their holds 1800/900/900/900/900 credited s; camera severities (Phase 17: frozen and view changed HIGH like an obstruction, degraded MEDIUM like a lost source, proximity LOW) and the choice that signed camera interference is `VISUAL` modality evidence; half-lives 3600/1800/3600/900/1800 s; credit cap 45 s; episode gap 30 s; correlation window 60 s; replay threshold 3 in 600 s; staleness ramp 15 → 150 s and stale cap after 45 s; hysteresis +5; recovery guards 50 / 85 (section 7.1); duplicate-id memory 5000.

**D. Future parameters requiring empirical tuning** (and the data that would be needed):

| Parameters | What is unknown | Data needed |
|---|---|---|
| factor weights, cap ceilings, severity points | relative importance of the evidence classes; whether 20 points for a lone tamper (before its cap) is sensible | real incident and fault data from the ESP32 prototype; expert/threat-model review; sensitivity analysis |
| confidence floor 0.30, exponent 2, correlation minimum 0.5, token multiplier 0.5 | YOLO confidence is a detector score, not a calibrated probability; the floor and exponent have no calibration | labelled scenes, a calibration curve of detector confidence against ground truth for the deployed camera and model |
| pressure points and cap 25, replay threshold | real forged/replay rates, how much trust-denial is acceptable | traffic captures from a real deployment; false-positive study |
| half-lives, holds, credit cap | recovery speed (section 7.1 ramp of about 30-80 minutes) versus attacker "wait it out" risk | recovery drills with real hardware, operator requirements |
| staleness ramp 15/45/150 s, offline timeout | real ESP32 reporting cadence and Wi-Fi jitter | ESP32 heartbeat logs |
| correlation window 60 s | physical-to-visual delay of a real tamper | staged physical tests |
| camera-health thresholds (`ai/vision/config.py` `HealthConfig`: sustain 2 s, similarity 0.7, shift 10 %, frozen 10 frames over 3 s, blur 0.2, low light 0.6) and proximity thresholds (`ProximityConfig`: 35 % of the frame, growth x2 in 2 s) | false-alarm and miss rates for the deployed camera, lens, lighting and scene | staged covering, turning, freezing and approach tests with the deployed camera; a day of normal footage for false alarms |
| coverage policy (nothing today) | whether TRUSTED should require a minimum coverage (section 4.7, implication 1) | design decision plus review, not data alone |
| sensor limits, expected firmware/config | per-deployment | digital twin / configuration management (later phase) |
