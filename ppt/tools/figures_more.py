"""Additional diagrams (11-17). Imported and run by make_figures.py.

Status vocabulary used everywhere (never blurred):
  IMPLEMENTED = code exists and is covered by automated tests (or a recorded real run)
  DESIGNED    = written down (docs / decisions / skeleton) but no working, validated code
  PLANNED     = not started
"""
import json
import subprocess
import sys
from collections import Counter

from make_figures import (AMBER, AMBER_BG, BG, BLUE, BLUE_BG, GREEN, GREEN_BG, GREY, GREY_BG, MUTED, PANEL, RED, ROOT,
                          TEXT, FancyBboxPatch, arrow, box, canvas, save)

DESIGN, DESIGN_BG = "#A78BFA", "#1E1A3A"   # DESIGNED (documented, not built)


def _collect_counts():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="], cwd=ROOT,
                         capture_output=True, text=True).stdout
    return Counter(l.split("::")[0] for l in out.splitlines() if "::" in l)


def pill(ax, x, y, w, text, fc, ec, fs=10.5, h=3.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1,rounding_size=1.2", fc=fc, ec=ec, lw=1.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold", color=ec)


# ------------------------------------------------------------------ 11. ML-KEM session (sequence)
def pqc_session_flow():
    fig, ax = canvas(title="ML-KEM-768 session: vision service to gateway",
                     subtitle="Optional layer on top of signed observations. Composition of standard primitives, not TLS, not externally reviewed.")
    xl, xr = 30, 130
    for x, t, s in ((xl, "Vision service", "ML-DSA-65 signing key\npinned gateway KEM public key"),
                    (xr, "Gateway", "ML-KEM-768 key pair\nenrolled signer public keys")):
        box(ax, x - 22, 66, 44, 9, t, None, BLUE_BG, BLUE, fs=14)
        ax.text(x, 62.6, s, ha="center", va="top", fontsize=9.5, color=MUTED, linespacing=1.3)
        ax.plot([x, x], [58, 4], color="#22304D", lw=2, ls=(0, (4, 4)))
    steps = [
        (54, "L", "1  ML-KEM.Encaps(pinned gateway key) -> ciphertext + shared secret"),
        (47, "R", "2  init {ciphertext, nonce, timestamp, signer id} + ML-DSA-65 signature"),
        (40, "G", "3  gateway verifies signature FIRST, then freshness, then ML-KEM.Decaps"),
        (33, "B", "4  both: HKDF-SHA256 -> client key, server key, confirmation key"),
        (26, "Lr", "5  session id, server nonce, key-confirmation tag (HMAC-SHA256)"),
        (19, "C", "6  client checks the tag: wrong key or corrupted ciphertext => refuses to send"),
        (12, "R2", "7  AES-256-GCM(signed observation), strictly increasing counter"),
        (5.5, "G2", "8  gateway decrypts, then verifies the inner ML-DSA signature"),
    ]
    for y, kind, text in steps:
        if kind == "L":
            ax.text(xl - 22, y, text, fontsize=11, va="center", ha="left")
        elif kind in ("R", "R2"):
            arrow(ax, (xl + 1, y + 1.6), (xr - 1, y + 1.6), BLUE, label=text, lsize=10.5, off=(0, 2.6))
        elif kind == "Lr":
            arrow(ax, (xr - 1, y + 1.6), (xl + 1, y + 1.6), GREEN, label=text, lsize=10.5, off=(0, 2.6))
        elif kind in ("G", "G2"):
            ax.text(xr + 22, y, text, fontsize=10.5, va="center", ha="right", color=GREEN)
        elif kind == "B":
            ax.text(80, y, text, fontsize=11, va="center", ha="center", color=BLUE)
        elif kind == "C":
            ax.text(xl - 22, y, text, fontsize=10.5, va="center", ha="left", color=AMBER)
    ax.text(5, 1.4, "Not provided: gateway signatures (authenticity = possession of the pinned KEM key), session resumption, encrypted responses, "
                    "persistent sessions (in memory).", fontsize=10.5, color=AMBER)
    save(fig, "11_pqc_session_flow")


# ------------------------------------------------------------------ 12. observation authentication flow
def observation_auth_flow():
    fig, ax = canvas(title="Observation authentication: what is signed, what is checked",
                     subtitle="Implemented and tested. Signature covers a length-prefixed encoding of exact fields, never a JSON serialization.")
    ax.text(5, 71, "SIGN (vision service)", fontsize=15, fontweight="bold", color=BLUE)
    chain = [("Observation", "normalized schema:\nobject, confidence,\nzone, anomaly flag", GREEN_BG, GREEN),
             ("Signed fields", "version, algorithm, signer,\nsource, observation id,\ntimestamp, payload text", BLUE_BG, BLUE),
             ("ML-DSA-65 sign", "context string\nqshield/signed-observation/v1", BLUE_BG, BLUE)]
    for i, (t, s, fc, ec) in enumerate(chain):
        box(ax, 5 + i * 27, 46, 24, 21, t, s, fc, ec, fs=12, sfs=9.5)
        if i < 2:
            arrow(ax, (29.4 + i * 27, 56.5), (31.6 + i * 27, 56.5), MUTED)
    ax.text(5, 40, "Envelope = fields + signature (3309 bytes)", fontsize=11.5, color=MUTED)
    ax.text(5, 30, "Optionally carried inside an ML-KEM-768 / AES-256-GCM session.", fontsize=11.5, color=MUTED)
    ax.text(5, 20, "Every rejection is reason-coded in the security-event log;", fontsize=11.5, color=MUTED)
    ax.text(5, 16.4, "the HTTP answer to the caller stays generic (401 / 422 / 409).", fontsize=11.5, color=MUTED)
    ax.text(92, 71, "VERIFY (gateway), in this order", fontsize=15, fontweight="bold", color=GREEN)
    checks = [("1  protocol version + algorithm", "unsupported"), ("2  signer enrolled and active", "unknown / retired / revoked"),
              ("3  ML-DSA-65 signature over canonical bytes", "invalid_signature"), ("4  signed timestamp within +/-300 s", "stale / future"),
              ("5  payload parses as an observation", "malformed_payload"), ("6  metadata matches payload", "payload_metadata_mismatch"),
              ("7  signer authorised for this device + source", "signer_not_authorised"), ("8  observation id not seen before", "replay -> HTTP 409")]
    for i, (c, rej) in enumerate(checks):
        y = 63 - i * 7.3
        ax.add_patch(FancyBboxPatch((92, y - 2.5), 40, 5.3, boxstyle="round,pad=0.1,rounding_size=0.6", fc=PANEL, ec=GREEN, lw=1.6))
        ax.text(94, y + 0.1, c, fontsize=10.3, va="center")
        ax.text(134, y + 0.1, "reject: " + rej, fontsize=9.8, va="center", color=AMBER)
    ax.text(92, 4, "Signature is verified BEFORE the payload is parsed or the timestamp is trusted.", fontsize=11, color=MUTED)
    save(fig, "12_observation_auth_flow")


# ------------------------------------------------------------------ 13. implementation status
def implementation_status():
    fig, ax = canvas(title="Implementation status: implemented, designed, planned",
                     subtitle="Three different things. Implemented = code + automated tests or a recorded real run. Designed = written down only. Planned = not started.")
    cols = [
        ("IMPLEMENTED", GREEN, GREEN_BG, "-", [
            "Gateway: FastAPI + SQLite", "Device path: register, heartbeat, telemetry", "  (software device agent)",
            "HMAC-SHA256 auth + replay counters", "Encrypted credential store, token APIs",
            "Vision: webcam, YOLO11n, zones, camera health", "Observation schema + ingestion",
            "ML-KEM-768 + ML-DSA-65 (pqcrypto 1.0.0)", "Signed observations, ML-KEM session", "PQC key provisioning / rotation / revocation",
            "NIST ACVP + interop tests; 347/347 pass"]),
        ("DESIGNED (not built)", DESIGN, DESIGN_BG, "--", [
            "ESP32 endpoint architecture + HMAC profile", "ESP32 firmware skeleton (never compiled", "  against a board, not validated)",
            "Device state machine + recovery model", "Evidence-chain design (hash chain + signatures)",
            "Trust model outline (full spec pending)", "Digital-twin concept"]),
        ("PLANNED (not started)", AMBER, AMBER_BG, "--", [
            "Dynamic trust engine (Phase 4)", "Quarantine + session revocation on trust loss", "Recovery / re-authentication",
            "Evidence chain implementation", "Digital twin", "Dashboard", "Attack-simulation suite",
            "ESP32 hardware validation", "ESP32-side PQC feasibility (R1)"]),
    ]
    for i, (head, ec, fc, ls, items) in enumerate(cols):
        x = 5 + i * 50.5
        box(ax, x, 6, 47.5, 64, "", None, fc, ec, ls=ls)
        ax.text(x + 23.75, 65.5, head, ha="center", fontsize=15, fontweight="bold", color=ec)
        for j, it in enumerate(items):
            sub = it.startswith("  ")
            ax.text(x + (5.5 if sub else 3), 59 - j * 4.6, ("" if sub else "-  ") + it.strip(), fontsize=11 if not sub else 10.2,
                    va="center", color=(MUTED if sub else TEXT))
    save(fig, "13_implementation_status")


# ------------------------------------------------------------------ 14. validation flow
def validation_flow():
    kem = json.loads((ROOT / "tests/vectors/pqc/acvp_mlkem768.json").read_text())
    dsa = json.loads((ROOT / "tests/vectors/pqc/acvp_mldsa65_sigver.json").read_text())
    live = json.loads((ROOT / "docs/results/live-run-phase3.json").read_text())
    g = {x["function"]: len(x["tests"]) for x in kem["testGroups"]}
    decaps, keychecks = g["decapsulation"] + g["encapsulation"], g["encapsulationKeyCheck"] + g["decapsulationKeyCheck"]
    ndsa = len(dsa["testGroups"][0]["tests"])
    per = _collect_counts()
    total = sum(per.values())
    pqc_tests = per["tests/pqc/test_mlkem768_mldsa65_behaviour.py"]   # behaviour file only (ACVP and interop are separate stages)
    proto_tests = sum(v for k, v in per.items() if k in ("tests/security/test_signed_observations.py", "tests/security/test_pqc_session.py",
                                                         "tests/security/test_pqc_keystore.py", "tests/integration/test_vision_signed_sink.py"))
    fig, ax = canvas(title="Security validation flow", subtitle="How the PQC and authentication claims were checked. Evidence of correctness, not certification.")
    v = live["offline_reverification"]
    stages = [("NIST ACVP\nvectors", f"{decaps + keychecks + ndsa}", f"{decaps} decaps + {keychecks} key checks\n+ {ndsa} ML-DSA verifications", BLUE),
              ("Independent\nimplementation", "2-way", "pure-Python kyber-py /\ndilithium-py interoperate", BLUE),
              ("Behaviour\ntests", f"{pqc_tests}", "modified / wrong-key /\nmalformed inputs", BLUE),
              ("Protocol\ntests", f"{proto_tests}", "signed observations, sessions,\nkeys, provisioning", GREEN),
              ("Sabotage\ncheck", "fails", "tests fail if verify is forced\nto return true", GREEN),
              ("Real run", f"{live['observations_stored']}", "webcam observations signed;\naltered payload 401; replay 409", GREEN),
              ("Offline\nre-verification", f"{v['valid']}/{v['envelopes_checked']}", f"stored signatures valid;\n{v['altered_copies_rejected']}/{v['envelopes_checked']} altered copies rejected", GREEN)]
    w, gap, x0 = 19.0, 2.6, 4
    for i, (t, big, sub, c) in enumerate(stages):
        x = x0 + i * (w + gap) - (i * 0.0)
        ax.add_patch(FancyBboxPatch((x, 30), w, 34, boxstyle="round,pad=0.3,rounding_size=1.2", fc=PANEL, ec=c, lw=2.2))
        ax.text(x + w / 2, 59, t, ha="center", va="center", fontsize=11.5, fontweight="bold", linespacing=1.2)
        ax.text(x + w / 2, 46, big, ha="center", va="center", fontsize=25, fontweight="bold", color=c)
        ax.text(x + w / 2, 35, sub, ha="center", va="center", fontsize=8.6, color=MUTED, linespacing=1.3)
        if i < len(stages) - 1:
            arrow(ax, (x + w + 0.3, 47), (x + w + gap - 0.3, 47), MUTED)
    ax.text(5, 22, f"{total} of {total} automated tests pass (pytest, counted at build time). 182 of them pre-date Phase 3 and are unchanged.", fontsize=13.5, color=GREEN, fontweight="bold")
    ax.text(5, 16, "Not covered: keygen / signing / encapsulation known-answer tests (library takes no seed), pre-hash mode, side channels, audit.", fontsize=12, color=AMBER)
    ax.text(5, 11, "No FIPS 140 validation. Library verified on Windows x86-64 only. Signature tests were confirmed to fail when verification is sabotaged.", fontsize=12, color=AMBER)
    save(fig, "14_validation_flow")


# ------------------------------------------------------------------ 15. Next: Dynamic Trust Engine
def trust_next():
    fig, ax = canvas(title="Next: Dynamic Trust Engine", subtitle="Phase 4: next implementation. Specification first, code second. Nothing on this slide is implemented.")
    pill(ax, 118, 80.8, 38, "PHASE 4 - NEXT IMPLEMENTATION", AMBER_BG, AMBER, fs=11, h=4.2)
    ax.text(5, 71, "INPUTS", fontsize=13, fontweight="bold", color=MUTED)
    inputs = [("cryptographic authenticity", GREEN, "events exist today"), ("visual anomalies", GREEN, "real observations exist today"),
              ("recent security events", GREEN, "reason-coded log exists today"), ("physical tamper", AMBER, "schema field; simulated only"),
              ("sensor consistency", AMBER, "schema fields; simulated only"), ("integrity state", AMBER, "self-reported; not proof"),
              ("network behaviour", GREY, "not collected yet")]
    for i, (t, c, s) in enumerate(inputs):
        y = 63 - i * 7.9
        ax.add_patch(FancyBboxPatch((5, y - 3), 42, 6.0, boxstyle="round,pad=0.1,rounding_size=0.7", fc=PANEL, ec=c, lw=1.8))
        ax.text(7, y + 0.9, t, fontsize=12, va="center", fontweight="bold")
        ax.text(7, y - 1.5, s, fontsize=9.3, va="center", color=MUTED)
    for y in [63 - i * 7.9 for i in range(7)]:
        arrow(ax, (47.6, y), (57.4, 40), MUTED, lw=1.2, style="-")
    arrow(ax, (54.5, 40), (57.6, 40), MUTED, lw=2)
    box(ax, 58, 30, 24, 20, "OBSERVATIONS", "authenticated,\ntimestamped,\nreason-coded", GREEN_BG, GREEN, fs=13, sfs=10)
    arrow(ax, (82.4, 40), (87.6, 40), AMBER, "--")
    box(ax, 88, 30, 22, 20, "TRUST SCORE", "formula, weights,\ncaps: not defined yet", AMBER_BG, AMBER, ls="--", fs=13, sfs=10)
    arrow(ax, (110.4, 40), (115.6, 40), AMBER, "--")
    box(ax, 116, 24, 39, 32, "", None, AMBER_BG, AMBER, ls="--")
    ax.text(135.5, 52.5, "STATE MACHINE", ha="center", fontsize=13, fontweight="bold")
    for i, st in enumerate(["TRUSTED", "SUSPICIOUS", "QUARANTINED", "RECOVERING", "VERIFIED", "RECOVERED"]):
        pill(ax, 120 + (i % 2) * 17.5, 44 - (i // 2) * 7, 16, st, PANEL, AMBER, fs=8.8, h=4.6)
    ax.text(5, 6.5, "Legend:  green = signal exists today   amber = schema field or simulated only   grey = not collected", fontsize=11, color=MUTED)
    ax.text(5, 2.6, "Authenticity is one input, never the whole decision. No weights, thresholds or score have been chosen: the model is specified before any code.", fontsize=11.5, color=AMBER)
    save(fig, "15_trust_engine_next")


# ------------------------------------------------------------------ 16. ESP32 status
def esp32_status():
    fig, ax = canvas(title="ESP32 endpoint: transparent status",
                     subtitle="The physical endpoint is not yet validated. No ESP32-side post-quantum claim is made.")
    rows = [("Endpoint role and architecture prepared", "DESIGNED", DESIGN, DESIGN_BG),
            ("HMAC-SHA256 device profile: gateway verification + replay protection, tested with a software agent", "IMPLEMENTED (gateway)", GREEN, GREEN_BG),
            ("Firmware project exists: protocol-only skeleton (register, heartbeat)", "DRAFT, NOT VALIDATED", AMBER, AMBER_BG),
            ("Exact board / variant: no board connected yet, not confirmed", "OPEN", AMBER, AMBER_BG),
            ("Hardware validation: flashing, sensors, tamper switch, real telemetry", "NOT DONE", GREY, GREY_BG),
            ("ESP32-side PQC (ML-DSA verify / ML-KEM): feasibility experiment R1", "NOT CLAIMED - PENDING", GREY, GREY_BG)]
    for i, (t, st, ec, fc) in enumerate(rows):
        y = 68 - i * 9.6
        ax.add_patch(FancyBboxPatch((5, y - 4), 150, 8.0, boxstyle="round,pad=0.1,rounding_size=0.8", fc=PANEL, ec=MUTED, lw=1.2))
        ax.text(8, y + 0.2, t, fontsize=13.2, va="center")
        pill(ax, 118, y - 1.6, 35, st, fc, ec, fs=10.5, h=3.8)
    ax.text(5, 9, "ESP32 uses HMAC-SHA256 (symmetric, not post-quantum). Post-quantum cryptography is used today only on the vision-service / gateway path.", fontsize=12.5, color=AMBER, fontweight="bold")
    ax.text(5, 4.6, "R1 asks only whether ML-DSA-65 verification is practical on the board. It is a feasibility experiment, not a commitment.", fontsize=11.5, color=MUTED)
    save(fig, "16_esp32_status")


# ------------------------------------------------------------------ 17. roadmap
def roadmap():
    fig, ax = canvas(title="Roadmap", subtitle="Phases 0-3 are done. Everything after is planned; the trust-model specification comes before any trust code.")
    done = [("0  Foundation", "config, credentials,\nprotocol, tests"), ("1  Device slice", "gateway, HMAC auth,\nreplay, software agent"),
            ("2  Vision", "webcam, YOLO11n,\nzones, observations"), ("3  PQC layer", "ML-KEM-768, ML-DSA-65,\nsigned observations")]
    plan = [("4A  Trust spec", "inputs, formula,\ncaps, state machine"), ("4  Trust engine", "explainable score,\nreasons"), ("5  Attack sim", "local scenarios"),
            ("6  Quarantine", "states, revocation"), ("7  Recovery", "safe mode, re-auth,\nvalidation"), ("8  Evidence", "hash chain +\nsignatures"),
            ("9-10  Twin, UI", "digital twin,\ndashboard")]
    w = 15.5
    for i, (t, s) in enumerate(done):
        x = 5 + i * (w + 1.2)
        box(ax, x, 52, w, 17, t, s, GREEN_BG, GREEN, fs=10.8, sfs=8.8)
    ax.text(5, 72.6, "DONE", fontsize=12, fontweight="bold", color=GREEN)
    ax.text(76, 72.6, "PLANNED (in order)", fontsize=12, fontweight="bold", color=AMBER)
    ww = 19
    for i, (t, s) in enumerate(plan):
        col, row = i % 4, i // 4
        x = 76 + col * (ww + 1.0)
        box(ax, x, 52 - row * 19, ww, 17, t, s, AMBER_BG, AMBER, ls="--", fs=10.5, sfs=9)
    arrow(ax, (71.0, 60.5), (75.6, 60.5), AMBER, "--")
    ax.text(5, 29.5, "PARALLEL TRACK (hardware)", fontsize=12, fontweight="bold", color=GREY)
    for i, (t, s) in enumerate([("Confirm ESP32 board", "no board connected yet"), ("Firmware validation", "flash, sensors, tamper"), ("R1 feasibility", "ML-DSA verify on ESP32?")]):
        box(ax, 5 + i * 26, 10, 24, 15, t, s, GREY_BG, GREY, ls="--", fs=11, sfs=9.3)
    ax.text(5, 4, "Order follows docs/implementation-roadmap.md. Cut order under time pressure: dashboard polish first.", fontsize=11.5, color=MUTED)
    save(fig, "17_roadmap")


def main():
    pqc_session_flow(), observation_auth_flow(), implementation_status(), validation_flow()
    trust_next(), esp32_status(), roadmap(), submission_architecture()


# ------------------------------------------------------------------ 18. compact architecture for the official template frame (4:3)
def submission_architecture():
    import matplotlib.pyplot as plt
    from make_figures import BG as _BG, DIAG_DEST
    fig = plt.figure(figsize=(12, 9), dpi=150, facecolor=_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 120), ax.set_ylim(0, 90), ax.axis("off")
    box(ax, 3, 66, 50, 19, "Vision service", "webcam + YOLO11n\nML-DSA-65 identity", BLUE_BG, BLUE, fs=24, sfs=19)
    box(ax, 3, 40, 50, 19, "ESP32 endpoint", "HMAC-SHA256\nNOT post-quantum", GREY_BG, GREY, fs=24, sfs=19)
    box(ax, 70, 46, 47, 39, "Gateway", "verifies before it stores:\nML-DSA-65 + HMAC,\nfreshness, replay", GREEN_BG, GREEN, fs=27, sfs=19)
    arrow(ax, (53.6, 75), (69.6, 70), BLUE, lw=3.5)
    arrow(ax, (53.6, 49), (69.6, 56), GREY, lw=3.5)
    ax.text(61.5, 81, "optional\nML-KEM\nsession", ha="center", va="center", fontsize=15, color=BLUE, linespacing=1.2)
    box(ax, 70, 30, 47, 11, "Observations + security events", None, GREEN_BG, GREEN, fs=18)
    arrow(ax, (93.5, 45.6), (93.5, 41.4), GREEN, lw=3)
    box(ax, 3, 4, 114, 20, "", None, AMBER_BG, AMBER, ls="--")
    ax.text(60, 19.5, "PLANNED (Phase 4+): dynamic trust engine", ha="center", fontsize=22, fontweight="bold", color=AMBER)
    ax.text(60, 11.5, "TRUSTED  /  SUSPICIOUS  /  QUARANTINED  ->  recovery", ha="center", fontsize=19, color=TEXT)
    arrow(ax, (93.5, 29.6), (93.5, 24.4), AMBER, "--", lw=3)
    ax.text(3, 30, "Solid = built and tested", fontsize=16, color=GREEN)
    ax.text(3, 26.5, "Dashed = planned", fontsize=16, color=AMBER)
    for ext in ("png", "svg"):
        fig.savefig(DIAG_DEST / f"18_submission_architecture.{ext}", facecolor=_BG)
    plt.close(fig)
    print("wrote 18_submission_architecture")
