# Claim audit

Performed 2026-09-24 on both decks (slide text and speaker notes), the text of every figure, and the presentation documents. `python ppt/tools/audit_claims.py` extracts every hit; raw hits are in `evidence/claim-audit-hits.json`. Each hit was then read and checked against the implementation. The scan decides nothing by itself.

## 1. Terms you asked to audit

| Term | Hits | Verdict |
|---|---|---|
| "quantum safe" / "quantum-safe" | 10 | All are **negations or instructions** ("Is the ESP32 quantum-safe? No", "Never say ..."). No affirmative use. |
| "quantum resistant" | 0 | Not used. The project name uses "Quantum-Resilient" (see 4). |
| "quantum proof" / "unhackable" / "100%" | 6 | Only in "never say" guidance. |
| "secure" / "security" | 66 | "security architecture", "security events", "post-quantum security layer", "security profiles" and endpoint names (`/secure`). One loose use ("secure observation layer") replaced with "authenticated observation layer". |
| "AI" / "AIoT" | 51 | Project name, "AI detection", "AI false positives", figure titles. No claim that AI decides compromise; slides state observations are not verdicts. |
| "self-healing" | 10 | Project name and one slide explicitly labelled PLANNED; notes say "recovery for defined compromise classes, not physical repair; not implemented". |
| "real-time" | 0 | Not used. |
| "novel" | 14 | Only as "no novel algorithm", "What is novel? the integration, proposed", "prior-art survey not done". No "first" or "novel" affirmation. |
| "first" | 22 | All ordinary ("specification comes first", "verify signature FIRST") or the negation "no 'first' claim". |
| "prevents" | 3 | Only the judge question "How do you prevent AI false positives?" answered "We do not claim to". No slide says the system prevents attacks. |
| "detects" / "detection" | 42 | Object detection (YOLO), "detection confidence", "not detectable yet", and "key-confirmation lets the client detect a wrong gateway key" (implemented and tested). No slide claims attack detection by the trust engine as built. |
| "guarantees" | 0 | Not used. |
| "protected" / "protection" | 14 | "replay protection" (implemented, tested), "is the channel protected?" (context question), "not protected (out of scope)" (limitation). "Post-quantum algorithms protect the path" was replaced with "ML-DSA-65 authenticates observations; the optional ML-KEM-768 session encrypts them". |
| "trust score" | 6 | Only in questions/negations, the planned box in figure 15, and "no trust score exists". |
| "accuracy" | 17 | All are "not measured" / "speed, not accuracy". |

## 2. Wording changes made by this audit
1. "Post-quantum algorithms protect the vision-service to gateway path" -> "ML-DSA-65 authenticates observations; the optional ML-KEM-768 session encrypts them" (deck notes, judge Q&A, figure 16).
2. "the secure observation layer" -> "the authenticated observation layer".
3. "a valid signature proves who produced an observation" -> "proves which key produced it / the holder of the signing key produced this exact observation" (figures 02, 09; judge Q&A).
4. "Authentication proves identity once" -> "establishes identity once".
5. Submission slide 2 "Every claim tested" -> "Built parts tested" (planned parts are not tested).
6. Submission slide 2 bullet "Continuous trust, not one-time authentication" -> "... (planned)".
7. Submission slide 5 "Economic: low-cost hardware" -> "no specialised hardware" (no cost figure exists to support "low-cost").
8. Footer on every full-deck slide: was the project's descriptive name; now "prototype: Phases 0-3 implemented; trust engine and recovery planned", so no slide implies capabilities the footer name might suggest.

## 3. Positive claims checked against evidence

| Claim on slides | Category | Verified against | Result |
|---|---|---|---|
| 347/347 tests pass; 182 pre-date Phase 3 | MEASURED | `evidence/pytest-summary.txt` (347 passed) | OK |
| ML-KEM-768 + ML-DSA-65 used vision service -> gateway | IMPLEMENTED | `backend/security/session.py`, `pqc_gateway.py`, tests, real run | OK |
| 35 decapsulation + 20 key-validity + 15 verification (3 valid, 12 invalid) agree with NIST | MEASURED | `tests/pqc/test_conformance_acvp.py`; chart counts read from the vector files | OK |
| Interop with pure-Python reference in both directions | MEASURED | `tests/pqc/test_interop_reference.py` | OK |
| 11 observations stored as `ML-DSA-65:vision-1`; altered payload 401; replay 409; 11/11 re-verified offline | MEASURED | `evidence/live-run-phase3.json` | OK. Caveat stated: no person in view; a replay after 300 s returns 401 (stale). |
| Modified, forged or replayed messages rejected and logged | IMPLEMENTED | `tests/security/test_device_auth.py`, `test_signed_observations.py` | OK |
| 8 ordered gateway checks | IMPLEMENTED | `backend/security/pqc_gateway.py` | OK |
| PQC latencies and sizes | MEASURED | `evidence/pqc-benchmark.json` | OK (laptop only, stated) |
| 25.1 / 21.0 / 51.4 / 30.0 FPS, 5.6 MB, AGPL-3.0 | MEASURED | `ai/README.md` (asserted in the chart script), package/checkpoint metadata | OK. Labelled speed, not accuracy. |
| ESP32 authenticates with HMAC-SHA256, not PQC | IMPLEMENTED (gateway side) | `backend/protocol/envelope.py` | OK |
| ESP32 firmware skeleton exists but is unvalidated; board unconfirmed | DESIGNED | `hardware/esp32/` (never compiled against a board) | OK |
| Video frames never stored or transmitted | IMPLEMENTED | `ai/vision` sinks emit observations only; `ai/README.md` | OK |
| Attack demos run only against our own local gateway | IMPLEMENTED | `scripts/demo_forgery.py` refuses non-loopback (verified: exit 2). It is the only attack demo. | OK |
| Runs on a laptop + USB webcam | MEASURED | benchmarks, live run | OK |
| Session state in memory; single-host trust domain; token over plain HTTP | limitation | `backend/README.md`, `pqc/README.md` | OK |

## 4. Implemented vs designed vs planned: integrity check
- Figure 13 and slide 10 use three separate categories with different colours and line styles. "Designed" is used only for written-down items (ESP32 architecture, firmware skeleton, state-machine and recovery model TD-10, evidence-chain design TD-09, trust-model outline TD-08, digital-twin concept).
- The states TRUSTED / SUSPICIOUS / QUARANTINED / RECOVERING / VERIFIED / RECOVERED, "trust score", "recovery", "evidence chain", "digital twin" and "dashboard" appear only inside dashed/amber elements or under a PLANNED/DESIGNED tag (figures 01, 10, 13, 15, 17, 18; slides 4, 16, 17, 20). No slide shows a trust value, threshold, weight, state transition or dashboard mock-up.
- The full deck's every slide carries a status tag (IMPLEMENTED / MEASURED / DESIGNED / PLANNED / MIXED / CONTEXT) in the file and speaker notes; "MIXED" slides label each element.
- Slide 16 ("Next: Dynamic Trust Engine") is tagged PLANNED and shows no numbers.

## 5. Residual risks (not fixable by rewording)
- **Project name:** "Quantum-Resilient Self-Healing AIoT Security Architecture" is the official title you specified. It names an architecture; the title slide of each deck states that trust engine, quarantine and recovery are next. Consider whether the submission title field should carry "Self-Healing" before recovery exists.
- **Novelty:** the template asks for a "genuinely novel" idea. The decks say "proposed integration" and "no 'first' claim" because no prior-art survey exists. Do not strengthen this without that survey.
- **Template:** it is not confirmed that the located sample is the one for this submission (see `references/official-template-analysis.md`).
- **Visual QA** was done by rendering with the local Microsoft PowerPoint. Fonts (Arial, Calibri) and layout should be re-checked on the presentation machine.
- **Placeholders** (`[TEAM NAME]`, members, school, contact, problem statement number, track) must be filled by the team; a deck with brackets left in must not be submitted.
