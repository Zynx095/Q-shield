"""Build the final Q-SHIELD deck (12 slides) on the official Quant-A-Maze 3.O template.

    python ppt/tools/quantamaze_deck/build.py
    powershell -File ppt/tools/render_deck.ps1 -Pptx ppt/final/Q-SHIELD_QuantAMaze3.0_Final.pptx \
        -OutDir ppt/preview/quantamaze -Pdf ppt/final/Q-SHIELD_QuantAMaze3.0_Final.pdf

The template (ppt/Quant-A-Maze.pptx) is opened read-only. Every slide is a clone of one of its own pages, so the
logos, the orange band, the halftone strip and the bottom band are the organisers' original artwork. The submission
limit is 12 slides; the deck has exactly 12. The plan and the source of every number are in ppt/final/SLIDE_PLAN.md
and in each slide's speaker notes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit import (  # noqa: E402
    BODY_FONT, CARD, DARK, DEEP, INK, LEFT, MONO_FONT, MUTED, ORANGE, RULE, STRONG_FONT, TEXT, TINT, TITLE_FONT,
    WHITE, box, chip, clone_slide, drop_slides, elbow, footer, header, line, node, notes, rule, text,
)

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "ppt" / "Quant-A-Maze.pptx"
OUT = ROOT / "ppt" / "final" / "Q-SHIELD_QuantAMaze3.0_Final.pptx"
MAX_SLIDES = 12                      # submission limit

S1 = "1. Participant Information & Topic Name"
S2 = "2. Problem Definition"
S3 = "3. Proposed Solution & Execution Plan"
S4 = "4. Technical Design"
S5 = "5. Feasibility & Innovation"
S6 = "6. Expected Outcome"
MONO = {"font": MONO_FONT}
B = {"font": STRONG_FONT}


def is_watermark(shape) -> bool:
    return shape.shape_type == 6 and abs(shape.width / 914400 - 6.98) < 0.1 and abs(shape.height / 914400 - 5.06) < 0.1


def blank(prs, base, watermark=False):
    return clone_slide(prs, base, keep=lambda s: s.shape_type != 17 and (watermark or not is_watermark(s)))


def flow(slide, boxes, y, h, gap, x0=LEFT, **kw):
    """A left-to-right row of boxes with arrows. boxes: [(label, sub, width, style dict)]. Returns box geometry."""
    x, geo = x0, []
    for i, (label, sub, w, st) in enumerate(boxes):
        box(slide, x, y, w, h, label, sub, **{**kw, **st})
        geo.append((x, y, w, h))
        if i < len(boxes) - 1:
            line(slide, x + w + 0.04, y + h / 2, x + w + gap - 0.04, y + h / 2, lw=1.75)
        x += w + gap
    return geo


def table(slide, x, y, widths, rows, header_row, row_h=0.82, size=18, head_size=16, highlight=(), font=None):
    """Rows of text cells separated by hairlines; highlighted rows get an orange left bar."""
    cx = [x]
    for w in widths[:-1]:
        cx.append(cx[-1] + w)
    total = sum(widths)
    for i, (hx, w) in enumerate(zip(cx, widths)):
        text(slide, hx, y, w - 0.15, 0.4, header_row[i], size=head_size, color=MUTED, font=STRONG_FONT)
    rule(slide, x, y + 0.45, total, color=INK, lw=1.25)
    yy = y + 0.5
    for r, row in enumerate(rows):
        if r in highlight:
            box(slide, x - 0.18, yy + 0.06, 0.08, row_h - 0.12, fill=ORANGE, line=None, kind="rect")
        for i, (hx, w) in enumerate(zip(cx, widths)):
            cell = row[i]
            text(slide, hx, yy, w - 0.2, row_h, cell if isinstance(cell, list) else [[(cell, B if i == 0 else {})]],
                 size=size, anchor="m", spacing=1.0, after=0, font=font or BODY_FONT)
        yy += row_h
        rule(slide, x, yy, total, color=RULE, lw=0.75)
    return yy


# ============================================================================== 1. participant information
def s01_participant(prs):
    s = blank(prs, prs.slides[2], watermark=True)
    text(s, LEFT, 2.05, 10.4, 0.8, S1, size=36, color=INK, font=TITLE_FONT)
    y = 3.2
    for k in ("Team Name", "Team Lead Name", "Team Lead Contact No"):
        node(s, LEFT + 0.12, y + 0.27, r=0.08)
        text(s, LEFT + 0.4, y, 7.5, 0.55, [[(f"{k}  ", B), ("[ to fill ]", {"color": MUTED})]], size=24)
        y += 0.68
    text(s, LEFT + 0.4, y + 0.15, 7.5, 0.5, [[("Selected Track", B)]], size=24)
    y += 0.8
    for t in ("Quantum Machine Learning (QML)", "Post-Quantum Cryptography (PQC)", "Web3 & Blockchain",
              "Generative AI & Machine Learning"):
        pqc = "PQC" in t
        node(s, LEFT + 0.75, y + 0.24, r=0.1, fill=ORANGE if pqc else WHITE, line=None if pqc else RULE, lw=1.5)
        text(s, LEFT + 1.05, y, 7.0, 0.5, [[(t, {"font": STRONG_FONT if pqc else BODY_FONT,
                                                  "color": INK if pqc else MUTED})]], size=22)
        y += 0.55
    x = 11.0
    text(s, x, 3.2, 6.1, 1.3, "Q-SHIELD", size=72, color=INK, font=TITLE_FONT)
    text(s, x, 4.55, 6.1, 1.0, "Continuous device trust with post-quantum-signed evidence", size=26, color=TEXT,
         font=STRONG_FONT)
    rule(s, x, 5.85, 6.0, color=ORANGE, lw=2.0)
    text(s, x, 6.05, 6.1, 1.5, [[("Authentication answers ", {}), ("who are you", B), (" once.", {})],
                                [("Q-SHIELD keeps asking ", {}),
                                 ("can you still be trusted", {"font": STRONG_FONT, "color": DEEP}), (".", {})]],
         size=21, after=6)
    flow(s, [("Device", None, 1.7, {}), ("Gateway", None, 1.7, {}), ("Trust", None, 1.7, {"fill": ORANGE, "line": ORANGE})],
         y=7.9, h=0.75, gap=0.4, x0=x, size=19)
    text(s, x, 8.85, 6.1, 0.5, "ML-KEM-768 and ML-DSA-65 (FIPS 203, 204)", size=17, color=MUTED, font=MONO_FONT)
    notes(s, "Team fields are deliberately left as [ to fill ]: they were not supplied and must not be invented.\n"
             "One line: authentication answers who you are once; Q-SHIELD keeps asking whether you can still be trusted. "
             "Track: Post-Quantum Cryptography.")


# ============================================================================== 2. problem definition
def s02_problem(prs):
    s = blank(prs, prs.slides[3])
    header(s, S2, S2, "Problem description: authenticated is not the same as trustworthy", official=True)
    ya = 4.95
    line(s, 1.0, ya, 16.9, ya, lw=2.0)
    node(s, 1.45, ya, r=0.15, fill=INK)
    text(s, 0.75, 3.8, 1.4, 0.9, [[("t0", MONO)], [("authenticate", B)]], size=17, align="c", spacing=1.0, after=0)
    text(s, 0.75, 5.15, 1.4, 0.4, "trusted", size=15, align="c", color=MUTED)
    for label, ex in (("enclosure\nopened", 4.6), ("configuration\ndrift", 8.0), ("camera covered\nor turned", 11.4),
                      ("forged or\nreplayed", 14.8)):
        node(s, ex, ya, r=0.14, fill=ORANGE)
        text(s, ex - 1.3, 3.85, 2.6, 0.9, [[(t, B)] for t in label.split("\n")], size=18, align="c", spacing=1.0, after=0)
        text(s, ex - 1.3, 5.12, 2.6, 0.4, "still trusted", size=15, align="c", color=MUTED, font=MONO_FONT)
    yb = 5.75
    line(s, 4.45, yb, 14.95, yb, color=ORANGE, lw=3.0, arrow=False)
    line(s, 4.45, yb - 0.2, 4.45, yb, color=ORANGE, lw=3.0, arrow=False)
    line(s, 14.95, yb - 0.2, 14.95, yb, color=ORANGE, lw=3.0, arrow=False)
    text(s, 4.45, 5.83, 10.5, 0.45, [[("trust should change here", {"font": STRONG_FONT, "color": DEEP}),
                                      (", but authentication never asks again", {"color": MUTED})]], size=18, align="c")
    rows = [
        ("Forged or replayed message", "rejected, then forgotten", "bounded pressure (≤ 25); 3 replays in 10 min hold the score at 65"),
        ("Enclosure opened", "nothing to see", "physical factor CRITICAL; score held at 55"),
        ("Camera covered, frozen or turned", "nothing to see", "signed camera-health report; visual factor HIGH"),
        ("Tamper + visual evidence within 60 s", "nothing to see",
         [[("confirmed incident: score 30, ", B), ("quarantine", {"font": STRONG_FONT, "color": DEEP})]]),
        ("Quantum adversary recording traffic", "classical signatures forgeable later",
         "ML-DSA-65 signs the evidence; ML-KEM-768 keys the session"),
    ]
    table(s, 1.1, 6.45, [5.0, 3.6, 7.4], rows, ["Threat", "Authentication alone", "What Q-SHIELD adds"],
          row_h=0.6, size=17, head_size=15, highlight=(3,))
    notes(s, "Every compromise on the timeline happens AFTER a successful login, so the device keeps its access. The table "
             "is the threat model: no single signal quarantines; two independent authenticated signals do; unauthenticated "
             "noise is capped at 25 points. Requirements: continuous scoring, correlation, gateway enforcement, earned "
             "recovery, a tamper-evident record, post-quantum signatures on the evidence path. Constraints are on slide 10. "
             "Sources: docs/architecture/trust-engine.md sections 4.5, 5, 9.")


# ============================================================================== 3. proposed solution
def s03_architecture(prs):
    s = blank(prs, prs.slides[4])
    header(s, S3, S3, "Working principle: observe → verify → score → enforce → recover → prove, for every device",
           official=True)
    h = 0.95
    box(s, LEFT, 3.85, 2.75, h, "ESP32 / device agent", "simulated today", size=18, sub_size=15)
    box(s, 4.15, 3.85, 3.1, h, "Identity", "HMAC-SHA256 + counter", size=18, sub_size=15, sub_font=MONO_FONT)
    line(s, LEFT + 2.79, 4.32, 4.11, 4.32, lw=1.75)
    box(s, LEFT, 5.35, 2.75, h, "Vision service", "camera + YOLO11n", size=18, sub_size=15)
    box(s, 4.15, 5.35, 3.1, h, "PQC session", "ML-KEM-768, AES-256-GCM", size=18, sub_size=15, sub_font=MONO_FONT)
    box(s, 7.75, 5.35, 3.0, h, "Signed observations", "ML-DSA-65", size=18, sub_size=15, sub_font=MONO_FONT,
        fill=TINT, line=ORANGE)
    line(s, LEFT + 2.79, 5.82, 4.11, 5.82, lw=1.75)
    line(s, 7.29, 5.82, 7.71, 5.82, lw=1.75)
    box(s, 11.3, 3.85, 2.55, 2.45, "Gateway", "authenticate\nenforce\nrecord", size=20, sub_size=15)
    elbow(s, [(7.29, 4.32), (11.26, 4.32)], lw=1.75)
    line(s, 10.79, 5.82, 11.26, 5.82, lw=1.75)
    box(s, 14.35, 3.85, 2.75, 2.45, "Trust engine", "six factors\ncaps, decay\nstate machine", size=20, sub_size=15,
        fill=INK, line=INK, color=WHITE, sub_color=WHITE)
    line(s, 13.89, 5.07, 14.31, 5.07, lw=1.75)
    box(s, 14.62, 6.68, 2.2, 1.2, "Decision", kind="diamond", size=16, fill=WHITE, line=INK, inset=0.02)
    line(s, 15.72, 6.34, 15.72, 6.64, lw=1.75)
    box(s, 14.2, 8.65, 2.9, 0.95, "TRUSTED or SUSPICIOUS", "normal access", fill=WHITE, line=INK, size=16, sub_size=14)
    line(s, 15.72, 7.9, 15.72, 8.61, lw=1.75)
    text(s, 15.8, 8.0, 1.3, 0.4, "≥ 50", size=14, color=MUTED, font=MONO_FONT)
    box(s, 11.3, 6.82, 2.55, 0.9, "QUARANTINE", "normal channel 403", fill=ORANGE, line=ORANGE, size=18, sub_size=14,
        sub_color=INK, sub_font=MONO_FONT)
    line(s, 14.6, 7.27, 13.89, 7.27, lw=1.75)
    text(s, 13.95, 6.82, 0.95, 0.4, "< 50", size=14, color=MUTED, font=MONO_FONT)
    box(s, 7.75, 6.82, 3.0, 0.9, "Recovery", "operator-started, verified", size=18, sub_size=14)
    line(s, 11.26, 7.27, 10.79, 7.27, lw=1.75)
    box(s, 4.15, 6.82, 3.1, 0.9, "VERIFIED → TRUSTED", "trust re-earned", size=18, sub_size=14)
    line(s, 7.71, 7.27, 7.29, 7.27, lw=1.75)
    box(s, LEFT, 8.4, 5.0, 1.15, "Digital twin", "expected vs self-reported state, used by trust and recovery",
        fill=CARD, line=None, size=18, sub_size=15, align="l", inset=0.2)
    box(s, 6.15, 8.4, 6.45, 1.15, "Evidence chain", "records every decision: SHA-256 linked, ML-DSA-65 signed",
        fill=CARD, line=None, size=18, sub_size=15, align="l", inset=0.2)
    notes(s, "Solution overview: a closed loop around every device: observe, verify, score, enforce, recover, prove. "
             "The device lane authenticates with HMAC; the vision lane uses an ML-KEM session carrying ML-DSA signed "
             "observations. The trust engine decides; the gateway enforces. Execution plan: built in 17 phases "
             "(slide 9). Sources: backend/api/app.py, backend/trust/, backend/recovery/.")


def s04_trust(prs):
    s = blank(prs, prs.slides[4])
    header(s, S3, "Core functionality: continuous six-factor trust")
    factors = [("Identity / crypto", 25), ("Physical", 20), ("Configuration integrity", 15), ("Sensor consistency", 15),
               ("Visual", 15), ("Network liveness", 10)]
    y = 3.5
    for name, w in factors:
        text(s, LEFT, y, 3.4, 0.6, [[(name, B)]], size=18, anchor="m")
        bw = 3.4 * w / 25
        box(s, 4.35, y + 0.15, bw, 0.32, None, fill=ORANGE, line=None, kind="rect")
        text(s, 4.35 + bw + 0.1, y, 0.9, 0.6, f"{w}%", size=18, font=STRONG_FONT, anchor="m")
        line(s, 8.5, y + 0.3, 8.65, y + 0.3, color=INK, lw=1.5, arrow=False)
        y += 0.68
    line(s, 8.65, 3.8, 8.65, 7.2, color=INK, lw=1.5, arrow=False)
    elbow(s, [(8.65, 3.95), (9.06, 3.95)], lw=1.75)
    box(s, 9.1, 3.5, 2.9, 0.9, "Weighted sum", "100 − Σ wᵢ·pᵢ", size=18, sub_size=15, sub_font=MONO_FONT)
    line(s, 10.55, 4.44, 10.55, 4.71, lw=1.75)
    box(s, 9.1, 4.75, 2.9, 0.9, "− Pressure", "unauthenticated, ≤ 25", size=18, sub_size=15, sub_font=MONO_FONT)
    line(s, 10.55, 5.69, 10.55, 5.96, lw=1.75)
    box(s, 9.1, 6.0, 2.9, 0.9, "min( caps )", "while a condition lasts", size=18, sub_size=15)
    line(s, 12.04, 6.45, 12.4, 6.45, lw=1.75)
    box(s, 12.45, 6.0, 1.55, 0.9, "SCORE", kind="oval", fill=INK, line=INK, color=WHITE, size=17)
    text(s, 12.45, 3.45, 4.7, 0.45, [[("Caps", B)]], size=18)
    yy = 3.9
    for name, v in (("Confirmed incident", 30), ("Physical tamper", 55), ("Correlated incident", 55),
                    ("Repeated replay", 65), ("Integrity mismatch", 65), ("Stale device", 79)):
        text(s, 12.45, yy, 2.55, 0.34, name, size=15, anchor="m")
        box(s, 15.0, yy + 0.08, 1.6 * v / 100, 0.18, None, fill=ORANGE if v < 50 else RULE, line=None, kind="rect")
        text(s, 15.0 + 1.6 * v / 100 + 0.06, yy, 0.6, 0.34, str(v), size=15, font=MONO_FONT, anchor="m")
        yy += 0.34
    text(s, 14.2, 6.0, 2.9, 1.0, [[("Authenticity is not trust:", {"font": STRONG_FONT, "color": DEEP})],
                                   [("a valid signature lets evidence count; it never adds points", {"color": MUTED})]],
         size=14, spacing=1.0, after=0)
    # state bands
    x0, w, yb = LEFT, 16.2, 7.75
    sc = w / 100
    box(s, x0, yb, 50 * sc, 0.6, "QUARANTINED  < 50", fill=DARK, line=DARK, color=WHITE, kind="rect", size=17)
    box(s, x0 + 50 * sc, yb, 30 * sc, 0.6, "SUSPICIOUS  50-79", fill=ORANGE, line=ORANGE, kind="rect", size=17)
    box(s, x0 + 80 * sc, yb, 20 * sc, 0.6, "TRUSTED  ≥ 80", fill=WHITE, line=INK, lw=2.0, kind="rect", size=17)
    line(s, x0 + 85 * sc, yb + 0.6, x0 + 85 * sc, yb + 0.82, lw=1.25, arrow=False)
    text(s, x0 + 85 * sc - 2.4, yb + 0.8, 4.8, 0.4, "back to TRUSTED only at 85 (hysteresis)", size=14, color=MUTED, align="c")
    text(s, LEFT, 9.2, 11.5, 0.8, [[("Recovery credit  ", B), ("Δc = clamp(t − max(t_prev, t_violation), 0, 45 s)", MONO)],
                                   [("only clean authenticated evidence earns time; silence never heals a device",
                                     {"color": MUTED})]], size=16, after=0, spacing=1.0)
    notes(s, "Weights from TD-08 (design choices, not calibrated). final = min(raw - pressure, caps); every change lists the "
             "reasons that sum exactly to the delta. Unavailable factors are excluded and reported, never assumed healthy. "
             "Caps and thresholds: trust-engine.md sections 5 and 7. The only cap below the quarantine line is the "
             "confirmed incident (30).")


# ============================================================================== 4. technical design
def s05_pqc(prs):
    s = blank(prs, prs.slides[5])
    header(s, S4, S4, "Post-quantum session: ML-KEM-768 key exchange, ML-DSA-65 signed, AES-256-GCM data", official=True)
    x = LEFT
    for i, (c, w) in enumerate(zip(["Why PQC", "ML-KEM", "Session", "ML-DSA", "Signed evidence", "AES-GCM", "Continuous trust"],
                                   [1.65, 1.65, 1.65, 1.65, 2.55, 1.75, 2.75])):
        hot = c in ("ML-KEM", "ML-DSA")
        box(s, x, 3.7, w, 0.58, c, fill=ORANGE if hot else WHITE, line=ORANGE if hot else INK, size=17)
        if i < 6:
            line(s, x + w + 0.03, 3.99, x + w + 0.27, 3.99, lw=1.5)
        x += w + 0.3
    lx, rx, w = LEFT, 11.85, 5.25
    text(s, lx, 4.45, w, 0.4, [[("Vision service (client)", B)]], size=17, align="c")
    text(s, rx, 4.45, w, 0.4, [[("Gateway (server)", B)]], size=17, align="c")
    line(s, lx + w / 2, 4.85, lx + w / 2, 8.3, color=RULE, lw=1.0, arrow=False, dash=True)
    line(s, rx + w / 2, 4.85, rx + w / 2, 8.25, color=RULE, lw=1.0, arrow=False, dash=True)
    st = dict(size=17, sub_size=14, sub_font=MONO_FONT)
    box(s, rx, 4.9, w, 0.62, "1  Key generation", "ML-KEM-768, provisioned once", **st)
    line(s, rx - 0.05, 5.21, lx + w + 0.05, 5.21, color=MUTED, lw=1.25, dash=True)
    text(s, 6.4, 4.82, 5.2, 0.38, "pinned public key, 1184 B", size=14, color=MUTED, font=MONO_FONT, align="c")
    box(s, lx, 5.6, w, 0.62, "2  Encapsulation", "→ shared secret + ciphertext", **st)
    line(s, lx + w + 0.05, 6.12, rx - 0.05, 6.12, lw=1.75)
    text(s, 6.3, 5.72, 5.4, 0.38, [[("ciphertext 1088 B + nonce + time", MONO)]], size=14, align="c")
    text(s, 6.3, 6.15, 5.4, 0.38, [[("signed with ML-DSA-65", {"font": STRONG_FONT, "color": DEEP})]], size=14, align="c")
    box(s, rx, 6.3, w, 0.62, "3  Verify + decapsulation", "→ shared secret, 32 B", **st)
    box(s, lx, 7.05, rx + w - lx, 0.62, "4  HKDF-SHA256, on both sides",
        "salt = both nonces, info = transcript  →  client→server, server→client, confirmation keys",
        fill=TINT, line=ORANGE, **st)
    line(s, rx - 0.05, 8.12, lx + w + 0.05, 8.12, lw=1.75)
    text(s, 6.2, 7.73, 5.6, 0.38, [[("session id + server nonce + confirmation", MONO)]], size=14, align="c")
    box(s, lx, 8.35, w, 0.62, "5  Confirm", "wrong key → nothing sent", size=17, sub_size=14)
    text(s, 6.3, 8.38, 5.4, 0.6, "standard primitives composed by us: not TLS, not externally reviewed", size=14,
         color=MUTED, align="c", spacing=1.0)
    text(s, rx, 8.3, w, 0.7, [[("median, laptop: ", {"color": MUTED}), ("encaps 0.069 ms, decaps 0.091 ms", MONO)],
                              [("full handshake 10.0 ms", MONO)]], size=14, align="c", after=0)
    box(s, lx, 9.12, rx + w - lx, 0.6,
        "6  AES-256-GCM session   per-direction keys, 64-bit counters, AAD = session ‖ direction ‖ counter",
        fill=ORANGE, line=ORANGE, size=17, color=INK)
    notes(s, "Why PQC: Shor's algorithm breaks RSA and elliptic-curve signatures, so evidence signed classically today "
             "could be forged later. Standards: ML-KEM-768 FIPS 203, ML-DSA-65 FIPS 204, HKDF RFC 5869, AES-GCM "
             "SP 800-38D, SHA-256 FIPS 180-4. 1: the gateway's key pair is provisioned; the client pins its public key. "
             "2-3: encapsulation, ML-DSA-signed init, decapsulation. 4: HKDF derives separate keys per direction plus a "
             "confirmation key. 5: a wrong pinned key fails confirmation; nothing is sent. 6: strict counters; replay "
             "and reorder fail. Numbers: docs/results/pqc-benchmark.json (i7-13700HX, Python bindings). The ESP32 "
             "device path is HMAC-SHA256 and is not post-quantum.")


def s06_signed(prs):
    s = blank(prs, prs.slides[5])
    header(s, S4, "ML-DSA-65 signed observations and evidence chain")
    geo = flow(s, [("Observation", None, 2.6, {}), ("Canonical encoding", None, 2.95, {}),
                   ("ML-DSA-65 sign", None, 2.6, {"fill": ORANGE, "line": ORANGE}), ("Signature", "3309 B", 2.4, {}),
                   ("Gateway verify", None, 2.85, {"fill": INK, "line": INK, "color": WHITE})],
               y=3.5, h=0.8, gap=0.6, size=18, sub_size=14, sub_font=MONO_FONT)
    for (x, y, w, h), sub in zip(geo[:3], ["device, object, zone,\nconfidence, time", "length-prefixed fields,\nnever JSON",
                                            "context\nqshield/signed-observation/v1"]):
        text(s, x - 0.15, y + h + 0.05, w + 0.3, 0.7, sub, size=14, color=MUTED, font=MONO_FONT, align="c", spacing=1.0)
    vx = geo[-1][0] + geo[-1][2] / 2
    elbow(s, [(vx, 4.32), (vx, 5.27)], lw=1.5)
    elbow(s, [(vx, 4.9), (11.1, 4.9), (11.1, 5.27)], lw=1.5)
    box(s, 9.2, 5.3, 3.8, 0.95, "ACCEPT  200", "active signer, in scope, fresh, new", fill=WHITE, line=INK, lw=2.0,
        size=18, sub_size=14)
    box(s, 13.3, 5.3, 3.8, 0.95, "REJECT", "401 forged, unknown, retired, stale\n409 replayed", fill=TINT, line=ORANGE,
        size=18, sub_size=14)
    text(s, LEFT, 5.3, 8.0, 1.0, [[("Binds ", B), ("who", B), (" (signer, source, devices), ", {}), ("what", B),
                                   (" (every field) and ", {}), ("when", B), (" (signed time).", {})],
                                  [("median, laptop: ", {"color": MUTED}), ("sign 9.42 ms, verify 0.188 ms", MONO)]],
         size=16, after=2)
    rule(s, LEFT, 6.55, 16.2, color=RULE, lw=1.0)
    text(s, LEFT, 6.62, 12.0, 0.45, [[("Evidence chain: ", B), ("every decision, SHA-256 linked and ML-DSA-65 signed", {})]],
         size=18)
    bw = 3.6
    for i, n in enumerate(("N", "N+1", "N+2")):
        x = LEFT + i * (bw + 0.75)
        box(s, x, 7.15, bw, 1.62, None, fill=WHITE, line=INK, kind="rect", lw=1.5)
        text(s, x + 0.2, 7.2, bw - 0.3, 0.42, [[(f"Event {n}", B)]], size=17)
        text(s, x + 0.2, 7.62, bw - 0.3, 1.1, [
            [("prev_hash  ", {"color": MUTED}), ("h(" + {"N": "N−1", "N+1": "N", "N+2": "N+1"}[n] + ")", {})],
            [("event_hash ", {"color": MUTED}), (f"h({n})", {})],
            [("signature  ", {"color": MUTED}), ("ML-DSA-65", {"color": DEEP})]], size=14, font=MONO_FONT, after=1)
        if i < 2:
            line(s, x + bw + 0.05, 7.96, x + bw + 0.7, 7.96, lw=2.0)
    box(s, 13.95, 7.15, 3.15, 1.62, None, fill=CARD, line=None, kind="rect")
    text(s, 14.15, 7.2, 2.9, 1.55, [[("26", {"font": TITLE_FONT, "size": 40})], [("entries in the live demo, ", {}),
                                                                                ("VERIFIED", B)]], size=15, after=0)
    text(s, LEFT, 8.95, 16.2, 1.0, [
        [("Verification recomputes every hash and checks every signature: an edited, reordered or removed entry is found.", {})],
        [("Not anchored externally: cutting the tail needs an outside copy of the head; holding the database and the key "
          "together would allow a rewrite.", {"color": MUTED})]], size=15, after=2)
    notes(s, "Canonical length-prefixed encoding: signer and verifier can never disagree on formatting. Every rejection "
             "is a security event that only adds bounded pressure. Chain: backend/evidence/chain.py (context "
             "qshield/evidence/v1, gateway evidence key). The 26 entries are from the Phase 17 live webcam demo.")


def s07_vision(prs):
    s = blank(prs, prs.slides[5])
    header(s, S4, "AI vision security: the camera is part of the boundary")
    flow(s, [("Camera", "USB / built-in", 2.1, {}), ("YOLO11n", "object detector", 2.1, {}),
             ("Object, confidence, zone", None, 2.9, {}), ("Camera health", "is the camera OK?", 2.6, {}),
             ("Signed observation", "ML-DSA-65", 2.6, {"fill": ORANGE, "line": ORANGE, "sub_color": INK}),
             ("Trust engine", None, 1.9, {"fill": INK, "line": INK, "color": WHITE})],
         y=3.5, h=0.95, gap=0.4, size=17, sub_size=14)
    cards = [("Normal", "matches the reference view", "no report", "real"),
             ("Occluded", "dark, flat or blinded for 2 s", "HIGH", "hot"),
             ("Moved", "shifted, or similarity < 0.7", "HIGH", "hot"),
             ("Frozen", "the same frame again and again", "HIGH", "hot"),
             ("Degraded", "low light or blur", "MEDIUM", "real"),
             ("Too close", "box > 35% of frame; not a distance", "LOW", "real")]
    x, cw = LEFT, 2.5
    for i, (name, how, effect, kind) in enumerate(cards):
        px, py, pw, ph = x + 0.3, 4.75, cw - 0.6, 1.0
        box(s, px, py, pw, ph, None, fill=DARK if name == "Occluded" else WHITE, line=INK, kind="rect", lw=1.25)
        if name in ("Normal", "Degraded"):
            fill = RULE if name == "Normal" else CARD
            line(s, px + 0.1, py + 0.75, px + pw - 0.1, py + 0.75, color=MUTED, lw=1.25, arrow=False)
            box(s, px + 0.3, py + 0.35, 0.4, 0.4, None, fill=fill, line=None, kind="rect")
            box(s, px + 0.95, py + 0.18, 0.3, 0.57, None, fill=fill, line=None, kind="rect")
        elif name == "Moved":
            line(s, px + 0.1, py + 0.55, px + pw - 0.1, py + 0.55, color=MUTED, lw=1.25, arrow=False)
            box(s, px + 0.75, py + 0.15, 0.4, 0.4, None, fill=RULE, line=None, kind="rect")
            box(s, px + 0.3, py + 0.35, 0.4, 0.4, None, fill=None, line=ORANGE, kind="rect", dash=True)
        elif name == "Frozen":
            box(s, px + 0.12, py + 0.1, pw - 0.45, ph - 0.3, None, fill=CARD, line=MUTED, kind="rect", lw=1.0)
            box(s, px + 0.3, py + 0.22, pw - 0.45, ph - 0.3, None, fill=WHITE, line=MUTED, kind="rect", lw=1.0)
            text(s, px + 0.3, py + 0.22, pw - 0.45, ph - 0.3, "=", size=22, align="c", anchor="m", color=MUTED)
        elif name == "Too close":
            box(s, px + 0.15, py + 0.1, pw - 0.3, ph - 0.1, None, fill=None, line=DEEP, kind="rect", lw=2.0)
        text(s, x + 0.05, 5.8, cw - 0.1, 0.45, [[(name, B)]], size=18, align="c")
        text(s, x + 0.05, 6.22, cw - 0.1, 0.75, how, size=14, color=MUTED, align="c", spacing=1.0)
        chip(s, x + (cw - 1.25) / 2, 6.95, effect, w=1.25, kind=kind, size=14)
        if i < len(cards) - 1:
            line(s, x + cw - 0.25, 5.25, x + cw + 0.2, 5.25, color=RULE, lw=1.25)
        x += cw + 0.24
    box(s, LEFT, 7.75, 3.6, 0.85, "Tamper report", "HMAC-SHA256, device", size=17, sub_size=14)
    text(s, 4.55, 7.8, 0.6, 0.75, "+", size=30, align="c", anchor="m", font=TITLE_FONT)
    box(s, 5.2, 7.75, 4.05, 0.85, "Signed camera interference", "occluded, moved or frozen", size=17, sub_size=14,
        fill=TINT, line=ORANGE)
    line(s, 9.3, 8.17, 10.05, 8.17, lw=1.75)
    box(s, 10.1, 7.75, 3.9, 0.85, "Confirmed incident", "within 60 s → score 30", fill=ORANGE, line=ORANGE, size=17,
        sub_size=14, sub_color=INK)
    line(s, 14.05, 8.17, 14.5, 8.17, lw=1.75)
    box(s, 14.55, 7.75, 2.55, 0.85, "QUARANTINE", fill=INK, line=INK, color=WHITE, size=17)
    text(s, LEFT, 8.85, 16.2, 1.1, [
        [("Camera alone: a penalty, never quarantine. Camera + rule match from the same signer: one modality, so a "
          "stolen vision key cannot confirm an incident.", {})],
        [("Rule match = restricted class in a restricted zone (a policy, not a verdict). Live on a USB webcam, CPU, about "
          "5 frames/s; detection accuracy not measured.", {"color": MUTED})]], size=15, after=2)
    notes(s, "The detector reports; only the trust engine decides. The webcam has no key: the vision service holds the "
             "ML-DSA-65 identity. Camera measures (ai/vision/health.py): brightness, texture, a normalised thumbnail "
             "against the reference view over cells no detection overlaps, phase correlation, sharpness, frame "
             "difference; 2 s and 5 frames of agreement. Tested on synthetic frames; on the live USB camera a moving "
             "person produced no false camera-health report in 2 x 90 s. Covering, turning and freezing the real camera "
             "have not been staged. Proximity is image-space: no distance is measured.")


def s08_recovery(prs):
    s = blank(prs, prs.slides[5])
    header(s, S4, "Quarantine, digital twin and self-healing recovery")
    steps = [("Quarantine", ""), ("Authorize", "operator starts"), ("Remediate", "known-good config"),
             ("Health checks", "3 clean reports"), ("Twin match", "expected = reported"), ("Verified", "ramp begins"),
             ("Recovered", "score ≥ 50"), ("Trusted", "score ≥ 85")]
    x, w, gap = LEFT, 1.82, 0.2
    for i, (a, b) in enumerate(steps):
        fill = DARK if i == 0 else (ORANGE if a in ("Verified", "Recovered") else (INK if a == "Trusted" else WHITE))
        box(s, x, 3.5, w, 0.85, a, fill=fill, line=fill if fill != WHITE else INK,
            color=WHITE if fill in (DARK, INK) else INK, size=16)
        if b:
            text(s, x - 0.05, 4.4, w + 0.1, 0.4, b, size=14, color=MUTED, align="c", spacing=1.0)
        if i < len(steps) - 1:
            line(s, x + w + 0.01, 3.92, x + w + gap - 0.01, 3.92, lw=1.5)
        x += w + gap
    rail = 5.05
    for k in (1, 2, 3, 4, 5, 6):
        cx = LEFT + k * (w + gap) + w / 2
        line(s, cx, 4.8, cx, rail, color=DEEP, lw=1.25, arrow=False, dash=True)
    line(s, LEFT + w / 2, rail, LEFT + 6 * (w + gap) + w / 2, rail, color=DEEP, lw=1.5, arrow=False, dash=True)
    elbow(s, [(LEFT + w / 2, rail), (LEFT + w / 2, 4.39)], color=DEEP, lw=1.5, dash=True)
    text(s, LEFT + 1.4, 5.1, 14.8, 0.4, [[("any failure → QUARANTINED: ", {"font": STRONG_FONT, "color": DEEP}),
                                         ("an authenticated fault, the 15-min verification deadline, the 2-h ramp "
                                          "deadline, revocation", {})]], size=15)
    # digital twin
    text(s, LEFT, 5.75, 9.0, 0.45, [[("Digital twin: ", B), ("expected (operator) vs reported (authenticated)", {"color": MUTED})]],
         size=17)
    ok, bad = [[("MATCH", B)]], [[("MISMATCH", {"font": STRONG_FONT, "color": DEEP})]]
    rows = [("Firmware", [[("agent-0.1", MONO)]], [[("agent-0.1", MONO)]], ok),
            ("Configuration", [[("cfg-good-1", MONO)]], [[("cfg-tampered", MONO)]], bad),
            ("Capabilities", [[("tamper, temp, vib.", MONO)]], [[("same three", MONO)]], ok),
            ("Temperature", [[("−20 to 60 °C", MONO)]], [[("27.4 °C", MONO)]], ok),
            ("Tamper state", [[("closed", MONO)]], [[("open", MONO)]], bad)]
    table(s, LEFT + 0.2, 6.2, [2.3, 2.6, 2.3, 1.75], rows, ["Field", "Expected", "Reported", "Verdict"],
          row_h=0.6, size=15, head_size=14, highlight=(1, 4))
    # quarantine channels
    qx = 10.75
    text(s, qx, 5.75, 6.4, 0.45, [[("Quarantine at the gateway", B)]], size=17)
    for i, c in enumerate(("Normal channel", "Recovery channel")):
        text(s, 13.45 + i * 1.85, 6.22, 1.8, 0.4, c, size=14, color=MUTED, font=STRONG_FONT, align="c")
    y = 6.7
    for label, cells in (("TRUSTED, SUSPICIOUS,\nRECOVERED", [("allowed", WHITE, INK), ("not open", CARD, MUTED)]),
                         ("QUARANTINED,\nRECOVERING, VERIFIED", [("403 blocked", ORANGE, INK), ("allowed", WHITE, INK)]),
                         ("Forged message", [("401", DARK, WHITE), ("401", DARK, WHITE)])):
        text(s, qx, y, 2.65, 0.75, [[(t, B)] for t in label.split("\n")], size=14, anchor="m", spacing=1.0, after=0)
        for i, (t, fill, col) in enumerate(cells):
            box(s, 13.45 + i * 1.85, y + 0.06, 1.75, 0.63, t, fill=fill, line=INK if fill == WHITE else fill, color=col,
                size=15, kind="rect", lw=1.0)
        y += 0.78
    text(s, qx, 9.1, 6.35, 0.85, [[("Enforced after authentication: forged traffic can neither trigger quarantine nor "
                                    "bypass it.", {"color": MUTED})]], size=14)
    notes(s, "Recovery (backend/recovery/orchestrator.py): operator-started, remediation acknowledged, three clean health "
             "checks each judged on its own report, then trust rebuilt from fresh evidence: RECOVERED at 50, TRUSTED at "
             "85. Live demo, announced time-lapse: VERIFIED at 30, RECOVERED 80 after 30 min, TRUSTED 85 after 42 min. "
             "Twin example: the demo's expected state against a simulated configuration-mismatch attack and an open "
             "tamper switch. A match is evidence, not attestation. Enforcement: backend/security/enforcement.py.")


def s09_stack(prs):
    s = blank(prs, prs.slides[5])
    header(s, S4, "Technology stack and implementation plan", "Each technology with the role it plays")
    groups = [
        ("Cryptography", [("pqcrypto", "ML-KEM-768, ML-DSA-65"), ("cryptography", "AES-256-GCM, HKDF"),
                          ("hashlib, hmac", "SHA-256 chain, HMAC")]),
        ("AI / vision", [("OpenCV", "camera capture"), ("YOLO11n", "object detection"), ("NumPy", "camera-health checks")]),
        ("Backend", [("FastAPI, uvicorn", "gateway API"), ("Pydantic", "strict schemas"), ("Trust engine", "pure Python")]),
        ("Frontend", [("ES modules", "dashboard, no build"), ("Presentation", "one-screen live view")]),
        ("Database", [("SQLite", "events, observations, twin, evidence chain, trust state")]),
        ("Deployment", [("Laptop gateway", "optional TLS, named operators, roles")]),
        ("Hardware (planned)", [("ESP32", "firmware skeleton, not compiled"), ("BME280, MPU6050, reed switch", "sensors, tamper")]),
    ]
    pos = [(LEFT, 3.85, 3.9), (4.98, 3.85, 3.9), (9.06, 3.85, 3.9), (13.14, 3.85, 3.96),
           (LEFT, 6.05, 5.25), (6.35, 6.05, 5.25), (11.8, 6.05, 5.3)]
    for (x, y, w), (name, items) in zip(pos, groups):
        text(s, x, y, w, 0.5, [[(name, {"font": TITLE_FONT})]], size=22)
        rule(s, x, y + 0.52, w - 0.15, color=ORANGE, lw=1.75)
        text(s, x, y + 0.62, w - 0.1, 1.5, [[(a, B), ("  " + b, {"color": MUTED})] for a, b in items], size=15, after=3)
    text(s, LEFT, 8.15, 9.0, 0.4, [[("Implementation plan: built and tested in 17 phases", B)]], size=17)
    x = LEFT
    for i, (p, d, w) in enumerate((("Phases 0-3", "protocol, PQC", 2.4), ("Phase 4", "trust engine", 2.2),
                                   ("Phases 5-11", "attacks, quarantine, recovery, twin, evidence, demo", 5.4),
                                   ("Phases 12-17", "operators, UI, hardening, camera boundary", 5.0))):
        box(s, x, 8.62, w, 0.82, p, d, fill=CARD, line=None, size=16, sub_size=14, align="l", inset=0.15)
        if i < 3:
            line(s, x + w + 0.03, 9.03, x + w + 0.37, 9.03, color=ORANGE, lw=1.75)
        x += w + 0.4
    notes(s, "Every technology is listed with its role. YOLO11n and ultralytics are AGPL-3.0; the weights are not "
             "committed. The hardware column is planned, not built. Phase history: docs/IMPLEMENTATION_STATUS.md.")


# ============================================================================== 5. feasibility & innovation
def s10_feasible(prs):
    s = blank(prs, prs.slides[6])
    header(s, S5, S5, "Technical feasibility and performance: what is real, what is not yet, what was measured",
           official=True)
    chip(s, LEFT, 3.72, "Real and tested", w=2.6, kind="hot", size=16)
    real = ["ML-KEM-768, ML-DSA-65, AES-256-GCM, HKDF", "SHA-256 linked, signed evidence chain",
            "YOLO11n vision on a real USB webcam", "trust, quarantine and recovery engines",
            "digital twin, dashboard, camera preview"]
    y = 4.2
    for it in real:
        node(s, LEFT + 0.12, y + 0.22, r=0.08)
        text(s, LEFT + 0.38, y, 7.4, 0.45, it, size=17)
        y += 0.47
    chip(s, LEFT, 6.72, "Simulated or not yet", w=2.95, kind="sim", size=16)
    sim = ["device telemetry: labelled software agent", "ESP32 never compiled; no physical sensors",
           "no attestation; camera thresholds unvalidated", "single gateway (SQLite); chain not anchored"]
    y = 7.2
    for it in sim:
        node(s, LEFT + 0.12, y + 0.22, r=0.08, fill=WHITE, line=ORANGE)
        text(s, LEFT + 0.38, y, 7.4, 0.45, it, size=17)
        y += 0.47
    text(s, 9.1, 3.7, 8.0, 0.45, [[("Post-quantum operations, median ms (laptop CPU)", B)]], size=17)
    y = 4.2
    for name, v in (("ML-KEM-768 keygen", 0.060), ("ML-KEM-768 encapsulate", 0.069), ("ML-KEM-768 decapsulate", 0.091),
                    ("ML-DSA-65 verify", 0.188), ("ML-DSA-65 sign", 9.42), ("Full session handshake", 10.0)):
        text(s, 9.1, y, 3.3, 0.42, name, size=15, anchor="m")
        bw = max(0.03, v * 0.34)
        box(s, 12.45, y + 0.1, bw, 0.22, None, fill=ORANGE, line=None, kind="rect")
        text(s, 12.45 + bw + 0.08, y, 1.0, 0.42, f"{v:g}", size=15, font=MONO_FONT, anchor="m")
        y += 0.45
    line(s, 12.45, 4.15, 12.45, y, color=INK, lw=1.0, arrow=False)
    text(s, 9.1, y + 0.02, 8.0, 0.45, "Key exchange is about 100x cheaper than signing; nothing measured on an ESP32.",
         size=14, color=MUTED)
    tx = 9.1
    for big, lab in (("785", "Python tests\npassing"), ("40", "JavaScript tests\npassing"), ("70", "NIST ACVP\nvectors agree"),
                     ("53 µs", "per trust-engine\nupdate (mean)")):
        box(s, tx, 7.55, 1.92, 1.85, None, fill=CARD, line=None, kind="rect")
        text(s, tx + 0.12, 7.62, 1.75, 0.75, big, size=30, font=TITLE_FONT, color=INK)
        text(s, tx + 0.12, 8.45, 1.75, 1.3, lab, size=14, color=MUTED, spacing=1.0)
        tx += 2.0
    notes(s, "Hardware is an adapter, not a redesign: same envelope, gateway and trust engine; 7 byte-exact protocol test "
             "vectors (tests/vectors/envelope_v1_cases.json); an ESP32-CAM stream is a configuration change (not yet "
             "tried). Scalability, honestly: one gateway, one process, SQLite. PQC numbers: docs/results/pqc-benchmark.json. "
             "Trust engine: docs/results/trust_bench.json (52.6 us mean). Tests: 785 Python and 40 JS passing on "
             "2026-10-02; by area in docs/testing.md. ACVP: 35 ML-KEM decapsulation, 20 key checks, 15 ML-DSA "
             "verifications (pqc/README.md).")


def s11_usp(prs):
    s = blank(prs, prs.slides[6])
    header(s, S5, "Innovation / USP", "What one-time authentication cannot do, and how it holds up under abuse")
    pts = [("Continuous, explainable trust", "every change lists the reasons that sum to it"),
           ("Authenticity is not trust", "signatures decide what counts; they never add points"),
           ("Camera as a security boundary", "covered, frozen or turned is signed evidence"),
           ("Bounded griefing", "forged traffic is capped at 25 points: never quarantine"),
           ("Earned recovery, signed evidence", "post-quantum signatures on every decision")]
    y0 = 3.85
    line(s, LEFT + 0.3, y0 + 0.3, LEFT + 0.3, y0 + 0.3 + 4 * 1.1, color=ORANGE, lw=2.0, arrow=False)
    for i, (a, b) in enumerate(pts):
        y = y0 + i * 1.1
        node(s, LEFT + 0.3, y + 0.3, r=0.16, fill=ORANGE if i in (2, 3) else WHITE, line=ORANGE, lw=2.0)
        text(s, LEFT + 0.75, y, 7.0, 1.05, [[(a, {"font": STRONG_FONT, "size": 20})], [(b, {"color": MUTED, "size": 16})]],
             size=18, spacing=1.0, after=0)
    rows = [("Replayed handshake", "one-use nonce: one session only"),
            ("Replayed or reordered message", "strict counters: rejected"),
            ("Rejection flood", "300 forged → 8 rows; trust unchanged"),
            ("Persistent refusals", "30 refusals → 1 session (was 30)"),
            ("Session exhaustion", "cap 64; 20 handshakes/h; backoff"),
            ("Forged 'all clear' in quarantine", "401; stays QUARANTINED")]
    table(s, 9.3, 3.8, [4.1, 3.7], rows, ["Attack (tested)", "Result"], row_h=0.72, size=15, head_size=14, highlight=(2,))
    text(s, LEFT, 9.45, 16.2, 0.5, [[("The novelty is the loop, not one algorithm. A prior-art survey has not been done: "
                                      "we claim an integration of standard mechanisms.", {"color": MUTED})]], size=15)
    notes(s, "Highlighted: the camera treated as part of the boundary, and the bounded-griefing guarantee. Abuse results "
             "are test results: tests/security/test_pqc_session.py, tests/integration/test_vision_session_churn.py, "
             "tests/fullstack/test_rejection_flood.py, tests/fullstack/test_quarantine.py. Do not call any single "
             "mechanism novel.")


# ============================================================================== 6. expected outcome
def s12_outcome(prs):
    s = blank(prs, prs.slides[7])
    header(s, S6, S6, "Expected results: the live demo, end to end, and what comes next", official=True)
    y = 3.75
    for a, b in (("Forged observation", "REJECTED  401"), ("Replayed observation", "REJECTED  409")):
        box(s, LEFT, y, 3.4, 0.62, a, size=16)
        line(s, LEFT + 3.45, y + 0.31, LEFT + 3.95, y + 0.31, lw=1.75)
        box(s, LEFT + 4.0, y, 3.1, 0.62, b, fill=CARD, line=None, size=16, font=MONO_FONT)
        y += 0.75
    box(s, LEFT, 5.35, 3.4, 0.68, "Physical tamper", "HMAC report", size=16, sub_size=13)
    box(s, LEFT, 6.15, 3.4, 0.68, "Visual evidence", "ML-DSA-65 signed", size=16, sub_size=13, fill=TINT, line=ORANGE)
    elbow(s, [(LEFT + 3.45, 5.69), (LEFT + 3.72, 5.69), (LEFT + 3.72, 6.07)], arrow=False, lw=1.75)
    elbow(s, [(LEFT + 3.45, 6.49), (LEFT + 3.72, 6.49), (LEFT + 3.72, 6.07), (LEFT + 3.95, 6.07)], lw=1.75)
    box(s, LEFT + 4.0, 5.72, 3.1, 0.68, "Correlation", "within 60 s", size=16, sub_size=13)
    line(s, LEFT + 5.55, 6.44, LEFT + 5.55, 6.69, lw=1.75)
    box(s, LEFT + 4.0, 6.72, 3.1, 0.7, "QUARANTINE", "score 30", fill=ORANGE, line=ORANGE, size=17, sub_size=13, sub_color=INK)
    text(s, LEFT, 7.5, 7.6, 0.45, "Attacks are simulated and labelled; the webcam detections are real.", size=14, color=MUTED)
    cx, cy, cw, ch = 9.6, 3.85, 7.3, 3.25

    def ys(v):
        return cy + ch - v / 100 * ch
    box(s, cx, ys(50), cw, ch * 0.5, None, fill=CARD, line=None, kind="rect")
    box(s, cx, ys(80), cw, ch * 0.3, None, fill=TINT, line=None, kind="rect")
    for v in (0, 50, 80):
        text(s, cx - 0.6, ys(v) - 0.18, 0.5, 0.36, str(v), size=13, font=MONO_FONT, align="r", color=MUTED)
    text(s, cx + 0.08, ys(50) + 0.03, 2.5, 0.35, "quarantine", size=13, color=MUTED)
    text(s, cx + 0.08, ys(80) + 0.03, 2.5, 0.35, "suspicious", size=13, color=DEEP)
    pts = [("join", 100), ("webcam", 90), ("forged", 80), ("replay", 72), ("tamper", 30), ("verified", 30),
           ("recovered", 80), ("trusted", 85)]
    step = cw / (len(pts) - 1)
    coords = [(cx + i * step, ys(v)) for i, (_, v) in enumerate(pts)]
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        line(s, x1, y1, x2, y2, color=INK, lw=2.25, arrow=False)
    for (x, y_), (lab, v) in zip(coords, pts):
        node(s, x, y_, r=0.11, fill=ORANGE if v < 50 else WHITE, line=INK, lw=1.5)
        text(s, x - 0.5, y_ - 0.5 if v > 40 else y_ + 0.12, 1.0, 0.36, str(v), size=14, font=MONO_FONT, align="c")
        text(s, x - 0.65, cy + ch + 0.06, 1.3, 0.36, lab, size=13, align="c", color=MUTED)
    text(s, cx - 0.3, cy + ch + 0.42, cw + 0.6, 0.36, "Live run on the USB webcam, 2026-10-02; recovery in announced time-lapse",
         size=13, color=MUTED, align="c")
    rule(s, LEFT, 8.05, 16.2, color=ORANGE, lw=2.0)
    text(s, LEFT, 8.15, 7.9, 1.85, [
        {"runs": [("Future scope, with hardware", B)], "after": 3},
        {"runs": "compile and flash the ESP32; match the 7 test vectors", "bullet": True},
        {"runs": "reed switch, then BME280 and MPU6050", "bullet": True},
        {"runs": "stage camera tests, calibrate; anchor the evidence head", "bullet": True},
    ], size=15, after=1)
    text(s, 9.2, 8.15, 7.9, 1.85, [
        {"runs": [("Real-world impact", B)], "after": 3},
        {"runs": "labs, server rooms, critical sites: devices must keep earning trust", "bullet": True},
        {"runs": "every incident arrives with a signed, explainable trail", "bullet": True},
        {"runs": [("Authenticate once. Verify continuously. Recover only with evidence.",
                   {"font": TITLE_FONT, "size": 18})], "before": 4},
    ], size=15, after=1)
    notes(s, "Measured, Phase 17 run of scripts/demo_full.py --webcam --pace 2 --hold: 100 -> 90 (real detections of "
             "the presenter in the restricted zone) -> 80 (forged) -> 72 SUSPICIOUS (replay) -> 30 QUARANTINED (tamper + "
             "signed visual) -> VERIFIED 30 -> RECOVERED 80 (30 min credited) -> TRUSTED 85 (42 min). Presentation mode "
             "and a dashboard-against-API check passed on the same run. Limitations are on slide 10; the hardware "
             "path is docs/hardware/hardware-architecture.md section 2.")


SLIDES = [s01_participant, s02_problem, s03_architecture, s04_trust, s05_pqc, s06_signed, s07_vision, s08_recovery,
          s09_stack, s10_feasible, s11_usp, s12_outcome]


def main() -> int:
    assert len(SLIDES) <= MAX_SLIDES, "the submission allows at most 12 slides"
    prs = Presentation(str(TEMPLATE))
    n_template = len(prs.slides)
    before = len(prs.slides)
    for fn in SLIDES:
        fn(prs)
    made = list(prs.slides)[before:]
    drop_slides(prs, n_template)
    for i, s in enumerate(made, 1):
        footer(s, i, len(made))
    assert len(prs.slides) == len(SLIDES) <= MAX_SLIDES
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"wrote {OUT} ({len(prs.slides)} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
