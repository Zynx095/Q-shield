"""Build the final Q-SHIELD deck on the official Quant-A-Maze 3.O template.

    python ppt/tools/quantamaze_deck/build.py
    powershell -File ppt/tools/render_deck.ps1 -Pptx ppt/final/Q-SHIELD_QuantAMaze3.0_Final.pptx \
        -OutDir ppt/preview/quantamaze -Pdf ppt/final/Q-SHIELD_QuantAMaze3.0_Final.pdf

The template (ppt/Quant-A-Maze.pptx) is opened read-only. Every slide is a clone of one of its own pages, so the
logos, the orange band, the halftone strip and the bottom band are the organisers' original artwork. The plan and
the source of every number are in ppt/final/SLIDE_PLAN.md and in each slide's speaker notes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit import (  # noqa: E402
    BODY_FONT, CARD, DARK, DEEP, INK, LEFT, MONO_FONT, MUTED, ORANGE, RIGHT, RULE, STRONG_FONT, TEXT, TINT, TITLE_FONT,
    WHITE, box, chip, clone_slide, drop_slides, elbow, footer, header, line, node, notes, rule, text,
)

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "ppt" / "Quant-A-Maze.pptx"
OUT = ROOT / "ppt" / "final" / "Q-SHIELD_QuantAMaze3.0_Final.pptx"

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


def table(slide, x, y, widths, rows, header_row, row_h=0.82, size=18, head_size=16, highlight=()):
    """Rows of text cells separated by hairlines; highlighted rows get an orange left bar."""
    cx = [x]
    for w in widths[:-1]:
        cx.append(cx[-1] + w)
    total = sum(widths)
    for i, (hx, w) in enumerate(zip(cx, widths)):
        text(slide, hx, y, w - 0.15, 0.4, header_row[i], size=head_size, color=MUTED, font=STRONG_FONT)
    rule(slide, x, y + 0.45, total, color=INK, lw=1.25)
    yy = y + 0.55
    for r, row in enumerate(rows):
        if r in highlight:
            box(slide, x - 0.18, yy + 0.06, 0.08, row_h - 0.16, fill=ORANGE, line=None, kind="rect")
        for i, (hx, w) in enumerate(zip(cx, widths)):
            cell = row[i]
            text(slide, hx, yy, w - 0.2, row_h, cell if isinstance(cell, list) else [[(cell, B if i == 0 else {})]],
                 size=size, anchor="m", spacing=1.0, after=0)
        yy += row_h
        rule(slide, x, yy, total, color=RULE, lw=0.75)
    return yy


# ====================================================================================== section 1
def s_participant(prs, tpl):
    s = blank(prs, tpl.slides[2], watermark=True)
    text(s, LEFT, 2.05, 10.4, 0.8, S1, size=36, color=INK, font=TITLE_FONT)
    fields = [("Team Name", "[ to fill ]"), ("Team Lead Name", "[ to fill ]"), ("Team Lead Contact No", "[ to fill ]")]
    y = 3.2
    for k, v in fields:
        node(s, LEFT + 0.12, y + 0.27, r=0.08)
        text(s, LEFT + 0.4, y, 7.5, 0.55, [[(f"{k}  ", B), (v, {"color": MUTED})]], size=24)
        y += 0.68
    text(s, LEFT + 0.4, y + 0.15, 7.5, 0.5, [[("Selected Track", B)]], size=24)
    tracks = ["Quantum Machine Learning (QML)", "Post-Quantum Cryptography (PQC)", "Web3 & Blockchain",
              "Generative AI & Machine Learning"]
    y += 0.8
    for t in tracks:
        pqc = "PQC" in t
        node(s, LEFT + 0.75, y + 0.24, r=0.1, fill=ORANGE if pqc else WHITE, line=None if pqc else RULE, lw=1.5)
        text(s, LEFT + 1.05, y, 7.0, 0.5, [[(t, {"font": STRONG_FONT if pqc else BODY_FONT,
                                                  "color": INK if pqc else MUTED})]], size=22)
        y += 0.55
    # topic block, right
    x = 11.0
    text(s, x, 3.2, 6.1, 1.3, "Q-SHIELD", size=72, color=INK, font=TITLE_FONT)
    text(s, x, 4.55, 6.1, 1.0, "Continuous device trust with post-quantum-signed evidence", size=26, color=TEXT,
         font=STRONG_FONT)
    rule(s, x, 5.85, 6.0, color=ORANGE, lw=2.0)
    text(s, x, 6.05, 6.1, 1.5, [[("Authentication answers ", {}), ("who are you", {"font": STRONG_FONT}),
                                 (" once.", {})],
                                [("Q-SHIELD keeps asking ", {}), ("can you still be trusted", {"font": STRONG_FONT, "color": DEEP}),
                                 (".", {})]], size=21, after=6)
    flow(s, [("Device", None, 1.7, {}), ("Gateway", None, 1.7, {}), ("Trust", None, 1.7, {"fill": ORANGE, "line": ORANGE})],
         y=7.9, h=0.75, gap=0.4, x0=x, size=19)
    text(s, x, 8.85, 6.1, 0.5, "ML-KEM-768 and ML-DSA-65 (FIPS 203, 204)", size=17, color=MUTED, font=MONO_FONT)
    notes(s, "Team fields are deliberately left as [ to fill ]: they were not supplied and must not be invented.\n"
             "Say the one line: authentication answers who you are once; Q-SHIELD keeps asking whether you can still be "
             "trusted. Track: Post-Quantum Cryptography.")
    return s


# ====================================================================================== section 2
def s_problem(prs, tpl):
    s = blank(prs, tpl.slides[3])
    header(s, S2, S2, "Problem description: authenticated is not the same as trustworthy", official=True)
    text(s, LEFT, 3.75, 6.2, 5.8, [
        {"runs": [("A device passes authentication. Then:", B)], "after": 10},
        {"runs": "its enclosure is opened", "bullet": True},
        {"runs": "its configuration drifts", "bullet": True},
        {"runs": "its camera is covered or turned", "bullet": True},
        {"runs": "its messages are forged or replayed", "bullet": True, "after": 16},
        {"runs": [("One-time authentication still says ", {}), ("trusted", B), (".", {})], "after": 16},
        {"runs": [("Evidence recorded today must also stay unforgeable when quantum computers arrive.", {})]},
    ], size=22)
    # timeline
    x0, x1, ya = 7.3, 16.9, 6.55
    line(s, x0, ya, x1, ya, lw=2.0)
    node(s, 7.65, ya, r=0.16, fill=INK)
    text(s, 6.95, 4.95, 1.6, 1.0, [[("t0", MONO)], [("authenticate", B)]], size=18, align="c")
    text(s, 6.95, 6.9, 1.6, 0.5, "trusted", size=17, align="c", color=MUTED)
    events = [("enclosure\nopened", 9.6), ("configuration\ndrift", 11.75), ("camera\nblinded", 13.9), ("forged or\nreplayed", 16.0)]
    for label, ex in events:
        node(s, ex, ya, r=0.15, fill=ORANGE)
        text(s, ex - 1.05, 5.0, 2.1, 1.1, [[(t, B)] for t in label.split("\n")], size=19, align="c", spacing=1.0, after=0)
        text(s, ex - 1.05, 6.85, 2.1, 0.5, "still trusted", size=16, align="c", color=MUTED, font=MONO_FONT)
    # the bracket: where trust should have changed
    yb = 7.75
    line(s, 9.45, yb, 16.15, yb, color=ORANGE, lw=3.0, arrow=False)
    line(s, 9.45, yb - 0.25, 9.45, yb, color=ORANGE, lw=3.0, arrow=False)
    line(s, 16.15, yb - 0.25, 16.15, yb, color=ORANGE, lw=3.0, arrow=False)
    text(s, 9.45, 7.95, 6.7, 1.0, [[("trust should change here", {"font": STRONG_FONT, "color": DEEP})],
                                   [("but authentication never asks again", {"color": MUTED})]], size=20, align="c")
    notes(s, "The core problem: one-time authentication. Every compromise on this timeline happens AFTER a successful "
             "login, so the device keeps its access. Quantum point: signatures made today must stay unforgeable later "
             "(classical RSA/ECDSA signatures fall to Shor's algorithm).")
    return s


def s_threats(prs, tpl):
    s = blank(prs, tpl.slides[3])
    header(s, S2, "Why authentication alone is not enough", "Threat model: what each attack looks like, and what answers it")
    rows = [
        ("Forged message", "rejected, then forgotten", "security event + bounded pressure (at most 25 points)"),
        ("Replayed message or observation", "rejected, then forgotten", "pressure; 3 replays in 10 min hold the score at 65"),
        ("Enclosure opened (tamper switch)", "nothing to see", "physical factor CRITICAL; score held at 55"),
        ("Camera covered, frozen or turned", "nothing to see", "signed camera-health report; visual factor HIGH"),
        ("Tamper + visual evidence within 60 s", "nothing to see", [[("confirmed incident: score 30, ", B), ("quarantine", {"font": STRONG_FONT, "color": DEEP})]]),
        ("Quantum adversary recording traffic", "classical signatures forgeable later", "ML-DSA-65 signs the evidence; ML-KEM-768 keys the session"),
    ]
    table(s, LEFT + 0.2, 3.8, [5.0, 4.0, 7.0], rows, ["Threat", "Authentication alone", "What Q-SHIELD adds"],
          row_h=0.93, size=19, highlight=(4,))
    notes(s, "Read the highlighted row: no single signal quarantines; two independent authenticated signals do. "
             "Unauthenticated noise is capped at 25 points of pressure, so a flood can reach SUSPICIOUS at worst. "
             "Sources: docs/architecture/trust-engine.md sections 4.5, 5, 9.")
    return s


def s_requirements(prs, tpl):
    s = blank(prs, tpl.slides[3])
    header(s, S2, "Functional requirements and constraints", "What the system must do, and the limits it was built under")
    reqs = [("Continuous scoring", "six evidence factors, every change explained"),
            ("Cross-modal correlation", "two independent signals within 60 s confirm an incident"),
            ("Gateway enforcement", "quarantine blocks the device's normal channel"),
            ("Earned recovery", "health checks, then trust rebuilt from fresh evidence"),
            ("Tamper-evident record", "SHA-256 linked, ML-DSA-65 signed evidence chain"),
            ("Post-quantum evidence path", "ML-KEM-768 session, ML-DSA-65 signatures")]
    cons = [("IoT-class device", "device path is HMAC-SHA256, not post-quantum"),
            ("No hardware attestation", "device state is self-reported evidence"),
            ("Laptop gateway", "FastAPI + SQLite, single process"),
            ("No physical device yet", "telemetry comes from a labelled software agent"),
            ("Uncalibrated parameters", "weights and thresholds are documented design choices")]
    for col, (items, x, fill, title) in enumerate(((reqs, LEFT, ORANGE, "Functional requirements"),
                                                   (cons, 9.45, None, "Constraints"))):
        text(s, x, 3.75, 7.6, 0.5, [[(title, B)]], size=22)
        y = 4.45
        line(s, x + 0.12, y + 0.25, x + 0.12, y + 0.85 * (len(items) - 1) + 0.25, color=ORANGE if fill else RULE,
             lw=1.5, arrow=False)
        for k, v in items:
            node(s, x + 0.12, y + 0.25, r=0.11, fill=fill or WHITE, line=None if fill else MUTED, lw=1.5)
            text(s, x + 0.45, y, 7.2, 0.85, [[(k, B)], [(v, {"color": MUTED, "size": 17})]], size=20, spacing=1.0, after=0)
            y += 0.85
    notes(s, "Constraints are stated up front. The ESP32 path is HMAC because a microcontroller-class device was assumed "
             "unable to run ML-DSA cheaply; that is a design assumption, not a measurement.")
    return s


# ====================================================================================== section 3
def s_loop(prs, tpl):
    s = blank(prs, tpl.slides[4])
    header(s, S3, S3, "Solution overview: a closed loop around every device", official=True)
    cx, cy, rx, ry = 7.2, 6.45, 3.55, 2.05
    import math
    steps = [("OBSERVE", "device and camera"), ("VERIFY", "HMAC, ML-DSA-65"), ("SCORE", "trust engine"),
             ("ENFORCE", "quarantine at gateway"), ("RECOVER", "verified, earned"), ("PROVE", "signed evidence chain")]
    pos = []
    for i, _ in enumerate(steps):
        a = math.radians(90 - i * 60)
        pos.append((cx + rx * math.cos(a), cy - ry * math.sin(a)))
    def edge(px, py, dx, dy, hw=1.3, hh=0.47):
        t = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
        return px + dx * t, py + dy * t
    for i, ((px, py), (lab, sub)) in enumerate(zip(pos, steps)):
        nx, ny = pos[(i + 1) % 6]
        dx, dy = nx - px, ny - py
        d = math.hypot(dx, dy)
        ux, uy = dx / d, dy / d
        ax, ay = edge(px, py, ux, uy)
        bx, by = edge(nx, ny, -ux, -uy)
        line(s, ax + ux * 0.06, ay + uy * 0.06, bx - ux * 0.08, by - uy * 0.08, color=MUTED, lw=1.5)
    for i, ((px, py), (lab, sub)) in enumerate(zip(pos, steps)):
        hot = lab in ("ENFORCE", "RECOVER")
        box(s, px - 1.3, py - 0.47, 2.6, 0.94, lab, sub, fill=ORANGE if hot else WHITE, line=ORANGE if hot else INK,
            size=20, sub_size=15, sub_color=INK if hot else MUTED)
    box(s, cx - 1.05, cy - 0.5, 2.1, 1.0, "continuous\ntrust", fill=None, line=None, size=20, color=DEEP)
    text(s, 12.3, 3.85, 4.8, 4.8, [
        {"runs": [("Working principle", B)], "after": 10},
        {"runs": "Every message is authenticated before it counts", "bullet": True},
        {"runs": "Every decision is scored and explained", "bullet": True},
        {"runs": "Every block is enforced at the gateway", "bullet": True},
        {"runs": "Every change is signed into the chain", "bullet": True},
        {"runs": "Trust comes back only with fresh evidence", "bullet": True},
    ], size=20)
    text(s, LEFT, 9.12, 3.0, 0.45, [[("Execution plan", B)]], size=18)
    phases = [("Phases 0-3", "protocol, PQC"), ("Phase 4", "trust engine"), ("Phases 5-11", "attacks, quarantine, recovery, demo"),
              ("Phases 12-17", "operators, UI, hardening, camera boundary")]
    x = 3.1
    for i, (p, d) in enumerate(phases):
        w = [2.2, 2.2, 4.1, 4.6][i]
        box(s, x, 8.98, w, 0.78, p, d, fill=CARD, line=None, size=16, sub_size=14, align="l", inset=0.15)
        if i < 3:
            line(s, x + w + 0.03, 9.37, x + w + 0.27, 9.37, color=ORANGE, lw=1.75)
        x += w + 0.3
    notes(s, "The novelty is the loop, not one algorithm. Orange marks the two steps a plain authentication system "
             "lacks: enforcement and earned recovery. All 17 build phases are in docs/IMPLEMENTATION_STATUS.md.")
    return s


def s_architecture(prs, tpl):
    s = blank(prs, tpl.slides[4])
    header(s, S3, "Working principle: system architecture", "Two clients authenticate differently and never interchangeably")
    h = 0.95
    # device lane
    box(s, LEFT, 3.85, 2.75, h, "ESP32 / device agent", "simulated today", size=18, sub_size=15)
    box(s, 4.15, 3.85, 3.1, h, "Identity", "HMAC-SHA256 + counter", size=18, sub_size=15, sub_font=MONO_FONT)
    line(s, LEFT + 2.79, 4.32, 4.11, 4.32, lw=1.75)
    # vision lane
    box(s, LEFT, 5.35, 2.75, h, "Vision service", "camera + YOLO11n", size=18, sub_size=15)
    box(s, 4.15, 5.35, 3.1, h, "PQC session", "ML-KEM-768, AES-256-GCM", size=18, sub_size=15, sub_font=MONO_FONT)
    box(s, 7.75, 5.35, 3.0, h, "Signed observations", "ML-DSA-65", size=18, sub_size=15, sub_font=MONO_FONT,
        fill=TINT, line=ORANGE)
    line(s, LEFT + 2.79, 5.82, 4.11, 5.82, lw=1.75)
    line(s, 7.29, 5.82, 7.71, 5.82, lw=1.75)
    # gateway and trust engine
    box(s, 11.3, 3.85, 2.55, 2.45, "Gateway", "authenticate\nenforce\nrecord", size=20, sub_size=15)
    elbow(s, [(7.29, 4.32), (11.26, 4.32)], lw=1.75)
    line(s, 10.79, 5.82, 11.26, 5.82, lw=1.75)
    box(s, 14.35, 3.85, 2.75, 2.45, "Trust engine", "six factors\ncaps, decay\nstate machine", size=20, sub_size=15,
        fill=INK, line=INK, color=WHITE, sub_color=WHITE)
    line(s, 13.89, 5.07, 14.31, 5.07, lw=1.75)
    # decision fork
    box(s, 14.62, 6.68, 2.2, 1.2, "Decision", kind="diamond", size=16, fill=WHITE, line=INK, inset=0.02)
    line(s, 15.72, 6.34, 15.72, 6.71, lw=1.75)
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
    # side rail
    box(s, LEFT, 8.4, 5.0, 1.15, "Digital twin", "expected vs self-reported state, used by trust and recovery",
        fill=CARD, line=None, size=18, sub_size=15, align="l", inset=0.2)
    box(s, 6.15, 8.4, 6.45, 1.15, "Evidence chain", "records every decision: SHA-256 linked, ML-DSA-65 signed",
        fill=CARD, line=None, size=18, sub_size=15, align="l", inset=0.2)
    notes(s, "Walk the device lane (HMAC) and the vision lane (ML-KEM session carrying ML-DSA signed observations) into "
             "the gateway. The trust engine decides; the gateway enforces. Recovery returns the device to TRUSTED only "
             "after verification and fresh evidence. Sources: backend/api/app.py, backend/trust/, backend/recovery/.")
    return s


def s_factors(prs, tpl):
    s = blank(prs, tpl.slides[4])
    header(s, S3, "Core functionality: the six-factor trust model", "Each factor is scored from its own evidence")
    factors = [("Identity / crypto", "identity_crypto", 25), ("Physical", "physical", 20),
               ("Configuration integrity", "config_integrity", 15), ("Sensor consistency", "sensor_consistency", 15),
               ("Visual", "visual", 15), ("Network liveness", "network", 10)]
    y = 3.85
    for name, key, w in factors:
        text(s, LEFT, y, 3.9, 0.85, [[(name, B)], [(key, {"font": MONO_FONT, "color": MUTED, "size": 15})]], size=19,
             spacing=1.0, after=0)
        bw = 4.4 * w / 25
        box(s, 4.95, y + 0.17, bw, 0.5, None, fill=ORANGE, line=None, kind="rect")
        text(s, 4.95 + bw + 0.12, y + 0.12, 1.0, 0.6, f"{w}%", size=20, font=STRONG_FONT, anchor="m")
        y += 0.98
    # pipeline: one bracket gathers the six factors
    line(s, 10.2, 4.27, 10.2, 9.17, color=INK, lw=1.5, arrow=False)
    for k in range(6):
        line(s, 10.05, 4.27 + k * 0.98, 10.2, 4.27 + k * 0.98, color=INK, lw=1.5, arrow=False)
    elbow(s, [(10.2, 4.47), (11.06, 4.47)], lw=1.75)
    box(s, 11.1, 3.9, 3.0, 1.15, "Weighted sum", "100 − Σ wᵢ·pᵢ", size=19, sub_size=16, sub_font=MONO_FONT)
    line(s, 12.6, 5.09, 12.6, 5.41, lw=1.75)
    box(s, 11.1, 5.45, 3.0, 1.15, "− Pressure", "unauthenticated, ≤ 25", size=19, sub_size=16, sub_font=MONO_FONT)
    line(s, 12.6, 6.64, 12.6, 6.96, lw=1.75)
    box(s, 11.1, 7.0, 3.0, 1.15, "min( caps )", "30, 55, 65, 79", size=19, sub_size=16, sub_font=MONO_FONT)
    line(s, 12.6, 8.19, 12.6, 8.51, lw=1.75)
    box(s, 11.6, 8.55, 2.0, 1.25, "SCORE", "0-100", kind="oval", fill=INK, line=INK, color=WHITE, sub_color=WHITE, size=20,
        sub_size=16)
    text(s, 14.6, 3.9, 2.55, 5.8, [
        {"runs": [("Authenticity is not trust", {"font": STRONG_FONT, "color": DEEP})], "after": 8},
        {"runs": "A valid signature lets evidence count.", "after": 8},
        {"runs": "It never adds points: a perfect signer still scores at most 100.", "after": 8},
        {"runs": "Unavailable factors are excluded and reported, never assumed healthy."},
    ], size=17)
    notes(s, "Weights are from TD-08 and are design choices, not calibrated (trust-engine.md section 16). "
             "The final score is min(raw - pressure, caps); every change carries reasons that sum exactly to the delta.")
    return s


def s_scoring(prs, tpl):
    s = blank(prs, tpl.slides[4])
    header(s, S3, "Continuous trust scoring", "From a number to a state, with caps that hold while a condition lasts")
    x0, w, y = LEFT, 16.2, 3.85
    sc = w / 100
    box(s, x0, y, 50 * sc, 0.75, "QUARANTINED", fill=DARK, line=DARK, color=WHITE, kind="rect", size=19)
    box(s, x0 + 50 * sc, y, 30 * sc, 0.75, "SUSPICIOUS", fill=ORANGE, line=ORANGE, kind="rect", size=19)
    box(s, x0 + 80 * sc, y, 20 * sc, 0.75, "TRUSTED", fill=WHITE, line=INK, lw=2.0, kind="rect", size=19)
    for v in (0, 50, 80, 85, 100):
        xx = x0 + v * sc
        line(s, xx, y + 0.75, xx, y + 0.95, lw=1.25, arrow=False)
        text(s, xx - 0.4, y + 0.95, 0.8, 0.4, str(v), size=16, align="c", font=MONO_FONT)
    text(s, x0 + 85 * sc - 1.6, y + 1.3, 3.6, 0.4, "back to TRUSTED only at 85", size=15, color=MUTED, align="c")
    # formula
    box(s, LEFT, 5.95, 7.6, 2.55, None, fill=CARD, line=None, kind="rect")
    text(s, LEFT + 0.3, 6.15, 7.2, 2.3, [
        [("raw      = 100 − Σ wᵢ·pᵢ", {})],
        [("final    = min(raw − pressure, caps)", {})],
        [("pressure ≤ 25  ", {}), ("(can never quarantine alone)", {"font": BODY_FONT, "color": MUTED, "size": 16})],
        [("score    = round(final)", {})],
    ], size=20, font=MONO_FONT, after=6)
    # caps
    text(s, 9.1, 5.85, 8.0, 0.45, [[("Caps (ceiling while active)", B)]], size=19)
    caps = [("Confirmed incident", 30), ("Physical tamper", 55), ("Correlated incident", 55), ("Repeated replay", 65),
            ("Integrity mismatch", 65), ("Stale device", 79)]
    yy = 6.3
    for name, v in caps:
        text(s, 9.1, yy, 3.3, 0.42, name, size=17, anchor="m")
        box(s, 12.45, yy + 0.09, 4.0 * v / 100, 0.26, None, fill=ORANGE if v < 50 else RULE, line=None, kind="rect")
        text(s, 12.45 + 4.0 * v / 100 + 0.08, yy, 0.7, 0.42, str(v), size=17, font=MONO_FONT, anchor="m")
        yy += 0.42
    text(s, LEFT, 9.05, 16.2, 0.95, [
        [("Recovery credit:  ", B), ("Δc = clamp(t − max(t_prev, t_violation), 0, 45 s)", MONO)],
        [("Only clean, authenticated device evidence earns time. An interval containing a violation earns nothing; "
          "silence never heals a device.", {"color": MUTED, "size": 17})]], size=18, after=2)
    notes(s, "Thresholds TRUSTED >= 80, QUARANTINED < 50 and re-entry 85 (hysteresis). Caps from trust-engine.md section 5. "
             "The orange cap is the only one below the quarantine line: a confirmed incident quarantines regardless of "
             "weights.")
    return s


# ====================================================================================== section 4
def s_crypto(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, S4, "Technologies and algorithms: why post-quantum, and where each primitive works", official=True)
    chain = ["Why PQC", "ML-KEM", "Session", "ML-DSA", "Signed evidence", "AES-GCM", "Continuous trust"]
    x, wv = LEFT, [1.65, 1.65, 1.65, 1.65, 2.55, 1.75, 2.75]
    for i, (c, w) in enumerate(zip(chain, wv)):
        hot = c in ("ML-KEM", "ML-DSA")
        box(s, x, 3.75, w, 0.7, c, fill=ORANGE if hot else WHITE, line=ORANGE if hot else INK, size=18)
        if i < len(chain) - 1:
            line(s, x + w + 0.03, 4.1, x + w + 0.27, 4.1, lw=1.5)
        x += w + 0.3
    rows = [
        ("Session key", [[("ML-KEM-768", MONO)]], "FIPS 203", "vision service ↔ gateway"),
        ("Observation signatures", [[("ML-DSA-65", MONO)]], "FIPS 204", "vision service identity"),
        ("Evidence signatures", [[("ML-DSA-65", MONO)]], "FIPS 204", "gateway evidence key"),
        ("Key schedule", [[("HKDF-SHA256", MONO)]], "RFC 5869", "session keys, per direction"),
        ("Session data", [[("AES-256-GCM", MONO)]], "SP 800-38D", "observations in transit"),
        ("Chain links", [[("SHA-256", MONO)]], "FIPS 180-4", "evidence chain"),
        ("Device messages", [[("HMAC-SHA256", MONO)]], "RFC 2104", [[("ESP32 path, ", {}), ("not PQC", {"color": DEEP, "font": STRONG_FONT})]]),
    ]
    table(s, LEFT + 0.2, 4.85, [3.7, 2.9, 2.2, 3.6], rows, ["Use", "Algorithm", "Standard", "Where"], row_h=0.66, size=18)
    box(s, 13.95, 4.85, 3.15, 4.75, None, fill=CARD, line=None, kind="rect")
    text(s, 14.15, 5.0, 2.8, 4.5, [
        {"runs": [("70", {"font": TITLE_FONT, "size": 54, "color": INK})], "after": 0},
        {"runs": [("NIST ACVP vectors agree", B)], "after": 10},
        {"runs": "35 ML-KEM-768 decapsulation", "bullet": True, "size": 16},
        {"runs": "20 ML-KEM-768 key checks", "bullet": True, "size": 16},
        {"runs": "15 ML-DSA-65 verifications", "bullet": True, "size": 16, "after": 10},
        {"runs": [("Algorithm-level evidence, not a certification.", {"color": MUTED})], "size": 15},
    ], size=18)
    notes(s, "Why PQC: Shor's algorithm breaks RSA and elliptic-curve signatures, so evidence signed classically today "
             "could be forged later. pqcrypto 1.0.0 provides ML-KEM-768 and ML-DSA-65; the cryptography library provides "
             "AES-256-GCM and HKDF. ACVP counts from pqc/README.md. The device path is HMAC and is not post-quantum.")
    return s


def s_handshake(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "ML-KEM-768 handshake flow", "Vision service and gateway agree on session keys; the init is ML-DSA-65 signed")
    lx, rx, w = LEFT, 11.85, 5.25
    text(s, lx, 3.7, w, 0.45, [[("Vision service (client)", B)]], size=19, align="c")
    text(s, rx, 3.7, w, 0.45, [[("Gateway (server)", B)]], size=19, align="c")
    line(s, lx + w / 2, 4.15, lx + w / 2, 8.45, color=RULE, lw=1.0, arrow=False, dash=True)
    line(s, rx + w / 2, 4.15, rx + w / 2, 8.3, color=RULE, lw=1.0, arrow=False, dash=True)
    box(s, rx, 4.2, w, 0.78, "1  Key generation", "ML-KEM-768, provisioned once", size=18, sub_size=15, sub_font=MONO_FONT)
    line(s, rx - 0.05, 4.6, lx + w + 0.05, 4.6, color=MUTED, lw=1.25, dash=True)
    text(s, 6.4, 4.2, 5.2, 0.4, "pinned public key, 1184 B", size=15, color=MUTED, font=MONO_FONT, align="c")
    box(s, lx, 5.1, w, 0.78, "2  Encapsulation", "→ shared secret + ciphertext", size=18, sub_size=15, sub_font=MONO_FONT)
    line(s, lx + w + 0.05, 5.95, rx - 0.05, 5.95, lw=1.75)
    text(s, 6.4, 5.45, 5.2, 0.45, [[("ciphertext 1088 B + nonce + time", MONO)]], size=15, align="c")
    text(s, 6.4, 6.0, 5.2, 0.4, [[("signed with ML-DSA-65", {"font": STRONG_FONT, "color": DEEP})]], size=15, align="c")
    box(s, rx, 6.05, w, 0.78, "3  Verify + decapsulation", "→ shared secret, 32 B", size=18, sub_size=15, sub_font=MONO_FONT)
    box(s, lx, 7.05, rx + w - lx, 0.78, "4  HKDF-SHA256, on both sides", "salt = both nonces, info = transcript  →  client→server, server→client, confirmation keys",
        fill=TINT, line=ORANGE, size=18, sub_size=15, sub_font=MONO_FONT)
    line(s, rx - 0.05, 8.25, lx + w + 0.05, 8.25, lw=1.75)
    text(s, 6.2, 7.85, 5.6, 0.4, [[("session id + server nonce + confirmation", MONO)]], size=15, align="c")
    box(s, lx, 8.5, w, 0.75, "5  Confirm", "wrong key → nothing sent", size=18, sub_size=15)
    text(s, 6.3, 8.6, 5.4, 0.6, "standard primitives composed by us: not TLS, not externally reviewed", size=14,
         color=MUTED, align="c", spacing=1.0)
    box(s, lx, 9.35, rx + w - lx, 0.62, "6  AES-256-GCM session   per-direction keys, 64-bit counters, AAD = session ‖ direction ‖ counter",
        fill=ORANGE, line=ORANGE, size=17, color=INK)
    text(s, rx, 8.42, w, 0.85, [[("median, laptop: ", {"color": MUTED}), ("encaps 0.069 ms, decaps 0.091 ms", MONO)],
                                [("full handshake 10.0 ms", MONO)]], size=15, align="c", after=0)
    notes(s, "1: the gateway's ML-KEM-768 key pair is provisioned; the client pins its public key. 2-3: encapsulation, "
             "signed init, decapsulation. 4: HKDF-SHA256 derives separate keys per direction plus a confirmation key. "
             "5: a client that encapsulated to the wrong key sees a bad confirmation and refuses to send. 6: AES-256-GCM "
             "with strict counters; replayed or reordered messages fail. Numbers: docs/results/pqc-benchmark.json "
             "(i7-13700HX, Python bindings). Not TLS, not externally reviewed.")
    return s


def s_signed(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "ML-DSA-65 signed observation flow", "From a camera observation to an accepted or rejected record")
    geo = flow(s, [("Observation", None, 2.75, {}), ("Canonical encoding", None, 3.05, {}),
                   ("ML-DSA-65 sign", None, 2.75, {"fill": ORANGE, "line": ORANGE}), ("Signature", None, 2.45, {}),
                   ("Gateway verify", None, 3.0, {"fill": INK, "line": INK, "color": WHITE})],
               y=3.85, h=0.95, gap=0.55, size=19)
    subs = ["device, object, zone,\nconfidence, time", "length-prefixed fields,\nnever JSON", "context\nqshield/signed-observation/v1",
            "3309 B", ""]
    for (x, y, w, h), sub in zip(geo, subs):
        text(s, x - 0.1, y + h + 0.1, w + 0.2, 1.0, sub, size=15, color=MUTED, font=MONO_FONT, align="c", spacing=1.0)
    vx = geo[-1][0] + geo[-1][2] / 2
    tx = 11.7
    elbow(s, [(vx, 4.84), (vx, 5.45), (tx, 5.45), (tx, 8.55)], arrow=False, lw=1.5)
    line(s, tx, 6.55, 12.0, 6.55, lw=1.5)
    line(s, tx, 8.55, 12.0, 8.55, lw=1.5)
    box(s, 12.05, 5.95, 5.05, 1.2, "ACCEPT  200", "signer active and in scope, fresh, new\n→ stored → trust engine", fill=WHITE,
        line=INK, lw=2.0, size=20, sub_size=15, align="l", inset=0.25)
    box(s, 12.05, 7.45, 5.05, 1.85, "REJECT", None, fill=TINT, line=ORANGE, size=20, align="l", anchor="t", inset=0.25)
    text(s, 12.3, 7.95, 4.7, 1.8, [[("401  ", MONO), ("forged, unknown, retired, out of scope", {})],
                                   [("409  ", MONO), ("replayed observation", {})],
                                   [("401  ", MONO), ("stale or future (±300 s)", {})]], size=16, after=4)
    text(s, LEFT, 6.1, 10.4, 3.6, [
        {"runs": [("What the signature binds", B)], "after": 8},
        {"runs": "who: the enrolled signer, its source and its allowed devices", "bullet": True},
        {"runs": "what: every field, in a fixed byte order", "bullet": True},
        {"runs": "when: the signed timestamp, checked against the gateway clock", "bullet": True, "after": 12},
        {"runs": [("median, laptop: ", {"color": MUTED}), ("sign 9.42 ms, verify 0.188 ms", MONO)]},
    ], size=19)
    notes(s, "Canonical length-prefixed encoding means the signer and the verifier can never disagree on formatting. "
             "Every rejection is a security event that only adds bounded pressure. Numbers: pqc/README.md.")
    return s


def s_abuse(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "Session security and abuse resistance", "What an attacker can do to the transport, and what stops it")
    rows = [
        ("Replayed handshake", "one-use nonce, reserved atomically", "concurrent replay gets one session"),
        ("Replayed or reordered message", "strict 64-bit counters, AES-GCM tag", "replay and reorder rejected"),
        ("Gateway lost the session", [[("401 ", MONO), ("session_expired", MONO), (" → one re-handshake", {})]], "observation still delivered"),
        ("Persistent refusals", "drop that observation, keep the session", "30 refusals: 1 session (was 30)"),
        ("Session-table exhaustion", "gateway cap 64; client 20 handshakes/h, backoff 1-60 s", "budget holds under a loop"),
        ("Rejection flood", "3 samples per sender per 10 s, rest coalesced with counts", "300 forged messages: 8 rows"),
    ]
    table(s, LEFT + 0.2, 3.8, [4.4, 6.3, 5.3], rows, ["Attack", "Control", "Tested result"], row_h=0.93, size=18,
          highlight=(5,))
    notes(s, "Phase 17 hardening. The flood control keeps trust decisions identical: a test runs the same flood with "
             "sampling on and off and compares state, score, pressure, last violation time and holds. "
             "Tests: tests/fullstack/test_rejection_flood.py, tests/integration/test_vision_session_churn.py, "
             "tests/security/test_pqc_session.py.")
    return s


def s_vision(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "AI vision security", "The detector reports what it sees; only the trust engine decides what it means")
    flow(s, [("Camera", "USB / built-in", 2.1, {}), ("YOLO11n", "object detector", 2.1, {}),
             ("Object, confidence, zone", None, 2.9, {}), ("Camera health", "is the camera OK?", 2.6, {}),
             ("Signed observation", "ML-DSA-65", 2.6, {"fill": ORANGE, "line": ORANGE, "sub_color": INK}),
             ("Trust engine", None, 1.9, {"fill": INK, "line": INK, "color": WHITE})],
         y=3.85, h=1.15, gap=0.4, size=17, sub_size=14)
    # zone pictogram
    fx, fy, fw, fh = LEFT, 5.65, 5.6, 3.9
    box(s, fx, fy, fw, fh, None, fill=WHITE, line=INK, kind="rect", lw=1.5)
    box(s, fx + fw / 2, fy, fw / 2, fh, None, fill=TINT, line=None, kind="rect")
    line(s, fx + fw / 2, fy, fx + fw / 2, fy + fh, color=ORANGE, lw=1.5, arrow=False, dash=True)
    text(s, fx + 0.1, fy + 0.08, 2.6, 0.4, "monitored zone", size=15, color=MUTED)
    text(s, fx + fw / 2 + 0.1, fy + 0.08, 2.6, 0.4, "restricted zone", size=15, color=DEEP, font=STRONG_FONT)
    box(s, fx + 3.6, fy + 0.95, 1.2, 2.55, "person\n0.86", fill=None, line=DEEP, lw=2.0, kind="rect", size=15, color=DEEP)
    node(s, fx + 4.2, fy + 3.5, r=0.08, fill=DEEP)
    text(s, fx, fy + fh + 0.08, fw, 0.4, "anchor: bottom-centre of the box", size=14, color=MUTED, align="c")
    text(s, 7.1, 5.65, 10.0, 4.3, [
        {"runs": [("Rule match = restricted class in a restricted zone", B)], "after": 2},
        {"runs": [("a policy match, not an anomaly-detection verdict", {"color": MUTED})], "after": 12},
        {"runs": [("The webcam has no key", B)], "after": 2},
        {"runs": [("the vision service holds the ML-DSA-65 identity, scoped to its device", {"color": MUTED})], "after": 12},
        {"runs": [("Live on a USB webcam, CPU only", B)], "after": 2},
        {"runs": [("about 5 frames/s at the configured rate; detection accuracy not measured", {"color": MUTED})]},
    ], size=20)
    notes(s, "Phase 17 live run: USB camera index 1, YOLO11n on CPU, 449 frames in 90 s, no failed reads. Detection "
             "accuracy, precision and recall have not been measured and are not claimed.")
    return s


def s_camera(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "Camera tamper and anomaly model", "The camera is part of the security boundary, not just a detector")
    cards = [("Normal", "scene matches the reference view", "no report", "real"),
             ("Occluded", "dark with no scene left, flat, or blinded; held 2 s", "HIGH", "hot"),
             ("Moved", "shift found by phase correlation, or similarity < 0.7", "HIGH", "hot"),
             ("Frozen", "the same frame again and again", "HIGH", "hot"),
             ("Degraded", "low light with the scene still visible, or blur", "MEDIUM", "real"),
             ("Too close", "box over 35% of the frame; not a distance", "LOW", "real")]
    x, cw = LEFT, 2.5
    for i, (name, how, effect, kind) in enumerate(cards):
        px, py, pw, ph = x + 0.25, 3.85, cw - 0.5, 1.35
        box(s, px, py, pw, ph, None, fill=WHITE, line=INK, kind="rect", lw=1.25)
        if name == "Normal" or name == "Degraded":
            line(s, px + 0.1, py + 0.95, px + pw - 0.1, py + 0.95, color=MUTED, lw=1.25, arrow=False)
            box(s, px + 0.3, py + 0.45, 0.45, 0.5, None, fill=RULE if name == "Normal" else CARD, line=None, kind="rect")
            box(s, px + 1.05, py + 0.25, 0.35, 0.7, None, fill=RULE if name == "Normal" else CARD, line=None, kind="rect")
        elif name == "Occluded":
            box(s, px, py, pw, ph, None, fill=DARK, line=INK, kind="rect", lw=1.25)
        elif name == "Moved":
            line(s, px + 0.1, py + 0.75, px + pw - 0.1, py + 0.75, color=MUTED, lw=1.25, arrow=False)
            box(s, px + 0.75, py + 0.25, 0.45, 0.5, None, fill=RULE, line=None, kind="rect")
            box(s, px + 0.3, py + 0.45, 0.45, 0.5, None, fill=None, line=ORANGE, kind="rect", dash=True)
        elif name == "Frozen":
            box(s, px + 0.15, py + 0.15, pw - 0.5, ph - 0.4, None, fill=CARD, line=MUTED, kind="rect", lw=1.0)
            box(s, px + 0.35, py + 0.3, pw - 0.5, ph - 0.4, None, fill=WHITE, line=MUTED, kind="rect", lw=1.0)
            text(s, px + 0.35, py + 0.3, pw - 0.5, ph - 0.4, "=", size=26, align="c", anchor="m", color=MUTED)
        elif name == "Too close":
            box(s, px + 0.2, py + 0.12, pw - 0.4, ph - 0.12, None, fill=None, line=DEEP, kind="rect", lw=2.0)
        text(s, x + 0.1, 5.3, cw - 0.2, 0.5, [[(name, B)]], size=20, align="c")
        text(s, x + 0.1, 5.8, cw - 0.2, 1.3, how, size=15, color=MUTED, align="c", spacing=1.0)
        chip(s, x + (cw - 1.25) / 2, 7.1, effect, w=1.25, kind=kind)
        if i < len(cards) - 1:
            line(s, x + cw - 0.02, 4.52, x + cw + 0.24, 4.52, color=RULE, lw=1.25)
        x += cw + 0.24
    # correlation
    box(s, LEFT, 8.05, 3.6, 1.0, "Tamper report", "HMAC-SHA256, device", size=18, sub_size=15)
    text(s, 4.6, 8.15, 0.6, 0.8, "+", size=34, align="c", anchor="m", font=TITLE_FONT)
    box(s, 5.25, 8.05, 4.0, 1.0, "Signed camera interference", "occluded, moved or frozen", size=18, sub_size=15,
        fill=TINT, line=ORANGE)
    line(s, 9.3, 8.55, 10.05, 8.55, lw=1.75)
    box(s, 10.1, 8.05, 3.9, 1.0, "Confirmed incident", "within 60 s → score 30", fill=ORANGE, line=ORANGE, size=18,
        sub_size=15, sub_color=INK)
    line(s, 14.05, 8.55, 14.5, 8.55, lw=1.75)
    box(s, 14.55, 8.05, 2.55, 1.0, "QUARANTINE", fill=INK, line=INK, color=WHITE, size=18)
    text(s, LEFT, 9.25, 16.2, 0.75, [[("Camera alone: a penalty, never quarantine.  Camera + rule match from the same "
                                       "signer: one modality, so a stolen vision key cannot confirm an incident by itself.",
                                       {"color": MUTED})]], size=16)
    notes(s, "Measures (ai/vision/health.py): brightness, texture, a normalised 32x24 thumbnail compared with the "
             "reference view over cells no detection overlaps, phase correlation for shifts, Laplacian sharpness, "
             "frame-to-frame difference. Every state needs 2 s and 5 frames of agreement. Tested on synthetic frames; "
             "on the live USB camera a seated, moving person produced no false camera-health report in 2 x 90 s. "
             "Covering, turning and freezing the real camera have not been staged. Proximity is an image-space "
             "heuristic: no distance is measured.")
    return s


def s_twin(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "Digital twin", "Expected state, set by an operator, against what the device reports (authenticated)")
    ok, bad = [[("MATCH", {"font": STRONG_FONT})]], [[("MISMATCH", {"font": STRONG_FONT, "color": DEEP})]]
    rows = [
        ("Firmware", [[("agent-0.1", MONO)]], [[("agent-0.1", MONO)]], ok),
        ("Configuration", [[("cfg-good-1", MONO)]], [[("cfg-tampered-0000", MONO)]], bad),
        ("Capabilities", [[("tamper, temperature, vibration", MONO)]], [[("tamper, temperature, vibration", MONO)]], ok),
        ("Temperature", [[("−20 to 60 °C", MONO)]], [[("27.4 °C", MONO)]], ok),
        ("Tamper state", [[("closed", MONO)]], [[("open", MONO)]], bad),
    ]
    table(s, LEFT + 0.2, 3.85, [2.5, 3.9, 4.3, 1.95], rows, ["Field", "Expected (operator)", "Observed (device report)", "Verdict"],
          row_h=0.9, size=18, highlight=(1, 4))
    text(s, 14.4, 3.85, 2.7, 5.9, [
        {"runs": [("How it is used", B)], "after": 8},
        {"runs": "overrides the global trust expectations per device", "bullet": True, "size": 16},
        {"runs": "recovery checks judge each report on its own content", "bullet": True, "size": 16},
        {"runs": "the known-good state is frozen during recovery", "bullet": True, "size": 16, "after": 12},
        {"runs": [("A match is evidence, not attestation.", {"font": STRONG_FONT, "color": DEEP})], "size": 16},
    ], size=17)
    notes(s, "Example values: expected state from the demo (tests/fullstack/conftest.py EXPECTED); the observed column "
             "shows a simulated configuration-mismatch attack and an open tamper switch. A compromised device could lie "
             "in its self-report; there is no secure boot or attestation.")
    return s


def s_chain(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "Evidence chain and forensics", "Every decision is linked by SHA-256 and signed with ML-DSA-65")
    bx, bw = LEFT, 4.4
    for i, n in enumerate(("N", "N+1", "N+2")):
        x = bx + i * (bw + 1.1)
        box(s, x, 3.9, bw, 2.05, None, fill=WHITE, line=INK, kind="rect", lw=1.5)
        text(s, x + 0.25, 4.0, bw - 0.4, 0.5, [[(f"Event {n}", B)]], size=20)
        text(s, x + 0.25, 4.5, bw - 0.4, 1.7, [
            [("prev_hash  ", {"color": MUTED}), ("h(" + {"N": "N−1", "N+1": "N", "N+2": "N+1"}[n] + ")", {})],
            [("event_hash ", {"color": MUTED}), (f"h({n})", {})],
            [("signature  ", {"color": MUTED}), ("ML-DSA-65", {"color": DEEP})],
        ], size=17, font=MONO_FONT, after=4)
        if i < 2:
            line(s, x + bw + 0.05, 4.92, x + bw + 1.05, 4.92, lw=2.0)
            text(s, x + bw, 4.42, 1.1, 0.45, "links", size=14, color=MUTED, align="c")
    box(s, LEFT, 6.75, 7.7, 1.15, "Signature on every entry", "context qshield/evidence/v1, gateway evidence key",
        fill=TINT, line=ORANGE, size=19, sub_size=15, sub_font=MONO_FONT, align="l", inset=0.25)
    box(s, LEFT, 8.2, 7.7, 1.65, "Verification", "recompute every SHA-256 hash, check every signature\n→ an edited, reordered or removed entry is found",
        fill=INK, line=INK, color=WHITE, sub_color=WHITE, size=19, sub_size=15, align="l", inset=0.25)
    text(s, 9.3, 6.75, 7.8, 3.2, [
        {"runs": [("Live demo result", B)], "after": 4},
        {"runs": [("26", {"font": TITLE_FONT, "size": 44}), ("  entries, chain ", {}), ("VERIFIED", {"font": STRONG_FONT})], "after": 10},
        {"runs": [("Not anchored externally: cutting entries off the end needs an outside copy of the head to "
                   "detect, and whoever holds both the database and the evidence key could rewrite history.",
                   {"color": MUTED})], "size": 17},
    ], size=20)
    notes(s, "backend/evidence/chain.py. Tests cover edit, delete, reorder and forged signature. The 26 entries are from "
             "the Phase 17 live webcam demo run. External anchoring (TD-09) is not built.")
    return s


def s_enforce(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "Quarantine enforcement", "Applied at the gateway, after authentication, on three separate channels")
    cols = ["Normal channel\nregister, heartbeat, telemetry", "Recovery channel\nrecovery/report", "Control\noperators only"]
    x0, cw, rh = 5.6, 3.75, 1.25
    for i, c in enumerate(cols):
        head, sub = c.split("\n")
        text(s, x0 + i * cw, 3.8, cw - 0.2, 0.9, [[(head, B)], [(sub, {"font": MONO_FONT, "size": 14, "color": MUTED})]],
             size=19, align="c", spacing=1.0)
    rows = [("TRUSTED, SUSPICIOUS,\nRECOVERED", [("allowed", WHITE, INK), ("refused: not open", CARD, MUTED), ("named operator", WHITE, INK)]),
            ("QUARANTINED, RECOVERING,\nVERIFIED", [("403 blocked", ORANGE, INK), ("allowed", WHITE, INK), ("named operator", WHITE, INK)]),
            ("Forged or replayed\nmessage", [("401 before enforcement", DARK, WHITE), ("401 before enforcement", DARK, WHITE), ("401", DARK, WHITE)])]
    y = 4.85
    for label, cells in rows:
        text(s, LEFT, y, 4.5, rh, [[(t, B)] for t in label.split("\n")], size=18, anchor="m", spacing=1.0, after=0)
        for i, (t, fill, col) in enumerate(cells):
            box(s, x0 + i * cw, y + 0.08, cw - 0.2, rh - 0.16, t, fill=fill, line=INK if fill == WHITE else fill,
                color=col, size=18, kind="rect", lw=1.0)
        y += rh
    text(s, LEFT, 8.85, 16.2, 1.1, [
        [("Forged traffic can neither trigger quarantine nor bypass it: ", B),
         ("it is rejected by authentication before the policy runs.", {})],
        [("Blocked messages are not trust evidence; recovery-channel reports are.", {"color": MUTED})]], size=18)
    notes(s, "backend/security/enforcement.py decide(). Blocked attempts are logged (throttled) as "
             "quarantine_access_blocked. Live demo: normal telemetry 403, forged 'all clear' 401.")
    return s


def s_recovery(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "Self-healing recovery", "Trust is earned back with fresh evidence, never granted")
    steps = [("Quarantine", ""), ("Authorize", "operator starts"), ("Remediate", "known-good config, acked"),
             ("Health checks", "3 reports, each judged"), ("Twin match", "expected = reported"), ("Verified", "ramp begins"),
             ("Recovered", "score ≥ 50, access back"), ("Trusted", "score ≥ 85")]
    x, w, gap = LEFT, 1.82, 0.2
    for i, (a, b) in enumerate(steps):
        fill = DARK if i == 0 else (ORANGE if a in ("Verified", "Recovered") else (INK if a == "Trusted" else WHITE))
        col = WHITE if fill in (DARK, INK) else INK
        box(s, x, 3.95, w, 1.0, a, fill=fill, line=fill if fill != WHITE else INK, color=col, size=17)
        text(s, x - 0.05, 5.05, w + 0.1, 0.9, b, size=15, color=MUTED, align="c", spacing=1.0)
        if i < len(steps) - 1:
            line(s, x + w + 0.01, 4.45, x + w + gap - 0.01, 4.45, lw=1.5)
        x += w + gap
    # failure rail
    elbow(s, [(LEFT + 3 * (w + gap) + w / 2, 5.95), (LEFT + 3 * (w + gap) + w / 2, 6.55)], arrow=False, color=DEEP, dash=True)
    rail_y = 6.55
    line(s, LEFT + 1 * (w + gap) + w / 2, rail_y, LEFT + 6 * (w + gap) + w / 2, rail_y, color=DEEP, lw=1.5, arrow=False, dash=True)
    for k in (1, 2, 4, 5, 6):
        line(s, LEFT + k * (w + gap) + w / 2, 5.95, LEFT + k * (w + gap) + w / 2, rail_y, color=DEEP, lw=1.25, arrow=False, dash=True)
    elbow(s, [(LEFT + w / 2, rail_y), (LEFT + w / 2, 5.0)], color=DEEP, lw=1.5, dash=True)
    line(s, LEFT + 1 * (w + gap) + w / 2, rail_y, LEFT + w / 2, rail_y, color=DEEP, lw=1.5, arrow=False, dash=True)
    text(s, LEFT + 2.2, 6.65, 13.0, 0.5, [[("any failure → back to QUARANTINED: ", {"font": STRONG_FONT, "color": DEEP}),
                                          ("an authenticated fault, the 15-min verification deadline, the 2-h ramp deadline, revocation", {})]],
         size=16)
    text(s, LEFT, 7.55, 8.0, 2.4, [
        {"runs": [("Rules", B)], "after": 6},
        {"runs": "each health check judges that report alone: a stale twin field cannot pass it", "bullet": True},
        {"runs": "only the recovery channel stays open while quarantined", "bullet": True},
        {"runs": "software remediation only: it cannot repair hardware", "bullet": True},
    ], size=17)
    box(s, 9.6, 7.55, 7.5, 1.95, None, fill=CARD, line=None, kind="rect")
    text(s, 9.85, 7.65, 7.1, 2.2, [
        {"runs": [("Live demo (announced time-lapse)", B)], "after": 6},
        {"runs": [("health checks 3 of 3 → ", {}), ("VERIFIED", {"font": STRONG_FONT}), (" at score 30", {})]},
        {"runs": [("RECOVERED ", {"font": STRONG_FONT}), ("score 80 after 30 min of credited evidence", {})]},
        {"runs": [("TRUSTED ", {"font": STRONG_FONT}), ("score 85 after 42 min", {})]},
    ], size=17)
    notes(s, "backend/recovery/orchestrator.py. The trust ramp needs about 40 minutes of clean evidence at the documented "
             "parameters; the demo advances the gateway clock and says so (TIME-LAPSE). No parameter is changed.")
    return s


def s_stack(prs, tpl):
    s = blank(prs, tpl.slides[5])
    header(s, S4, "Technology stack", "Grouped by what each part does in the system")
    groups = [
        ("Cryptography", [("pqcrypto", "ML-KEM-768, ML-DSA-65"), ("cryptography", "AES-256-GCM, HKDF-SHA256"),
                          ("hashlib, hmac", "SHA-256 chain, HMAC device auth")]),
        ("AI / vision", [("OpenCV", "camera capture"), ("YOLO11n (ultralytics)", "object detection"),
                         ("NumPy", "camera-health statistics")]),
        ("Backend", [("FastAPI + uvicorn", "gateway API"), ("Pydantic", "strict schemas"),
                     ("Trust engine", "pure Python, deterministic")]),
        ("Frontend", [("Vanilla ES modules", "dashboard, no build step"), ("Presentation mode", "one-screen live view")]),
        ("Database", [("SQLite", "events, observations, twin, evidence chain, trust state")]),
        ("Deployment", [("One laptop gateway", "optional TLS, named operators")]),
        ("Hardware (planned)", [("ESP32", "firmware skeleton, not compiled"), ("BME280, MPU6050, reed switch", "sensors, tamper")]),
    ]
    cols = [(LEFT, 3.85, groups[0]), (6.4, 3.85, groups[1]), (11.9, 3.85, groups[2]),
            (LEFT, 7.1, groups[3]), (6.4, 7.1, groups[4]), (11.9, 7.1, groups[5])]
    for x, y, (name, items) in cols:
        text(s, x, y, 5.1, 0.5, [[(name, {"font": TITLE_FONT, "size": 24})]], size=24)
        rule(s, x, y + 0.55, 5.0, color=ORANGE, lw=1.75)
        text(s, x, y + 0.68, 5.1, 2.4, [[(a, B), ("  " + b, {"color": MUTED})] for a, b in items], size=17, after=6)
    hw = groups[6]
    box(s, 11.9, 9.05, 5.2, 0.85, None, fill=CARD, line=None, kind="rect")
    text(s, 12.05, 9.07, 5.0, 0.85, [[(hw[0] + ":  ", B), ("ESP32 skeleton (not compiled); BME280, MPU6050, reed switch", {"color": MUTED})]],
         size=15, anchor="m")
    notes(s, "Every technology is listed with its role. YOLO11n and ultralytics are AGPL-3.0; the weights are not "
             "committed. The hardware row is planned, not built.")
    return s


# ====================================================================================== section 5
def s_feasible(prs, tpl):
    s = blank(prs, tpl.slides[6])
    header(s, S5, S5, "Technical feasibility: what is real today, and what is simulated", official=True)
    real = ["ML-KEM-768 and ML-DSA-65 (pqcrypto)", "AES-256-GCM, HKDF-SHA256", "SHA-256 linked evidence chain",
            "YOLO11n vision on a real webcam", "trust engine and recovery engine", "digital twin and quarantine enforcement",
            "dashboard and browser camera preview"]
    sim = ["device telemetry (software agent, labelled)", "attacks (attack_simulation, labelled)", "ESP32 deployment",
           "physical sensors and tamper switch"]
    for x, title, items, kind in ((LEFT, "Real and tested", real, "real"), (9.45, "Simulated", sim, "sim")):
        chip(s, x, 3.82, title, w=2.6 if kind == "real" else 1.9, kind="hot" if kind == "real" else "sim", size=17)
        y = 4.45
        for it in items:
            node(s, x + 0.12, y + 0.24, r=0.09, fill=ORANGE if kind == "real" else WHITE, line=None if kind == "real" else ORANGE)
            text(s, x + 0.4, y, 7.3, 0.5, it, size=20)
            y += 0.58
    box(s, 9.45, 7.15, 7.65, 2.1, None, fill=CARD, line=None, kind="rect")
    text(s, 9.7, 7.25, 7.2, 2.6, [
        {"runs": [("Hardware is an adapter, not a redesign", B)], "after": 6},
        {"runs": "same envelope, same gateway, same trust engine", "bullet": True},
        {"runs": [("7 byte-exact protocol test vectors", {}), (" (tests/vectors)", MONO)], "bullet": True},
        {"runs": "ESP32-CAM stream: a configuration change (not yet tried)", "bullet": True},
    ], size=18)
    notes(s, "Distinguish real from simulated every time. Hardware readiness: docs/hardware/device-protocol.md, "
             "hardware-architecture.md, the vectors in tests/vectors/envelope_v1_cases.json checked by "
             "tests/security/test_device_vectors.py.")
    return s


def s_perf(prs, tpl):
    s = blank(prs, tpl.slides[6])
    header(s, S5, "Performance and testing", "Scalability and performance: measured numbers only")
    text(s, LEFT, 3.75, 8.4, 0.5, [[("Post-quantum operations, median ms (laptop CPU)", B)]], size=19)
    ops = [("ML-KEM-768 keygen", 0.060), ("ML-KEM-768 encapsulate", 0.069), ("ML-KEM-768 decapsulate", 0.091),
           ("ML-DSA-65 verify", 0.188), ("ML-DSA-65 sign", 9.42), ("Full session handshake", 10.0)]
    y, scale = 4.4, 4.0 / 10.0
    for name, v in ops:
        text(s, LEFT, y, 3.6, 0.55, name, size=17, anchor="m")
        bw = max(0.03, v * scale)
        box(s, 4.6, y + 0.13, bw, 0.3, None, fill=ORANGE, line=None, kind="rect")
        text(s, 4.6 + bw + 0.1, y, 1.5, 0.55, f"{v:g}", size=17, font=MONO_FONT, anchor="m")
        y += 0.62
    line(s, 4.6, 4.35, 4.6, y, color=INK, lw=1.0, arrow=False)
    text(s, LEFT, y + 0.05, 8.4, 0.9, [[("Key exchange is about 100 times cheaper than signing. i7-13700HX, Python "
                                         "bindings; nothing measured on an ESP32.", {"color": MUTED})]], size=15)
    tiles = [("785", "Python tests passing"), ("40", "JavaScript tests passing"), ("70", "NIST ACVP vectors agree"),
             ("53 µs", "trust-engine update (mean)")]
    tx, ty = 9.9, 3.8
    for i, (big, lab) in enumerate(tiles):
        x = tx + (i % 2) * 3.65
        yy = ty + (i // 2) * 1.75
        box(s, x, yy, 3.45, 1.55, None, fill=CARD, line=None, kind="rect")
        text(s, x + 0.2, yy + 0.08, 3.1, 0.85, big, size=40, font=TITLE_FONT, color=INK)
        text(s, x + 0.2, yy + 0.93, 3.1, 0.5, lab, size=16, color=MUTED)
    text(s, tx, 7.4, 7.2, 2.55, [
        {"runs": [("Tests by area", B)], "after": 4},
        {"runs": [("trust 235, security 149, AI 135, full stack 111, PQC 74, integration 47, twin 18, evidence 15", {})],
         "size": 16, "after": 8},
        {"runs": [("Scale, honestly: ", B), ("one gateway on SQLite, one process; multi-gateway is not built.", {})],
         "size": 16},
    ], size=17)
    notes(s, "PQC numbers: docs/results/pqc-benchmark.json (300 calls x 5 rounds). Trust engine: docs/results/trust_bench.json "
             "(52.6 us mean per apply; about 0.7 ms per gateway record). Tests: python -m pytest (785 passed) and "
             "node --test (40 passed) on 2026-10-02; counts per area from pytest --collect-only (docs/testing.md).")
    return s


def s_usp(prs, tpl):
    s = blank(prs, tpl.slides[6])
    header(s, S5, "Innovation / USP", "What Q-SHIELD does that one-time authentication cannot")
    pts = [("Continuous, explainable trust", "every score change lists the reasons that sum to it"),
           ("Authenticity is not trust", "signatures decide what counts; they never add points"),
           ("Camera as a security boundary", "covered, frozen or turned is signed evidence"),
           ("Bounded griefing", "forged traffic is capped at 25 points: it can never quarantine"),
           ("Earned recovery, signed evidence", "post-quantum signatures on every decision")]
    y0 = 4.0
    line(s, LEFT + 0.3, y0 + 0.3, LEFT + 0.3, y0 + 0.3 + 4 * 1.15, color=ORANGE, lw=2.0, arrow=False)
    for i, (a, b) in enumerate(pts):
        y = y0 + i * 1.15
        node(s, LEFT + 0.3, y + 0.3, r=0.17, fill=ORANGE if i in (2, 3) else WHITE, line=ORANGE, lw=2.0)
        text(s, LEFT + 0.8, y, 9.6, 1.1, [[(a, {"font": STRONG_FONT, "size": 23})], [(b, {"color": MUTED, "size": 18})]],
             size=20, spacing=1.0, after=0)
    box(s, 11.6, 4.0, 5.5, 3.55, None, fill=CARD, line=None, kind="rect")
    text(s, 11.85, 4.15, 5.1, 5.4, [
        {"runs": [("The novelty is the loop", B)], "after": 8},
        {"runs": "observe → verify → score → enforce → recover → prove", "font": MONO_FONT, "size": 16, "after": 12},
        {"runs": "Each mechanism is standard. Their integration around one device's continuous trust is the "
                 "contribution.", "after": 12},
        {"runs": [("A prior-art survey has not been done; we claim an integration, not a new algorithm.",
                   {"color": MUTED, "size": 16})]},
    ], size=18)
    notes(s, "Highlighted: the two points judges rarely see elsewhere: the camera treated as part of the boundary, and the "
             "bounded griefing guarantee. Do not call any single mechanism novel.")
    return s


# ====================================================================================== section 6
def s_results(prs, tpl):
    s = blank(prs, tpl.slides[7])
    header(s, S6, S6, "Expected results / prototype: the live demo, end to end", official=True)
    rows = [("Forged observation", "REJECTED  401", WHITE), ("Replayed observation", "REJECTED  409", WHITE)]
    y = 3.85
    for a, b, f in rows:
        box(s, LEFT, y, 3.4, 0.8, a, size=17)
        line(s, LEFT + 3.45, y + 0.4, LEFT + 4.0, y + 0.4, lw=1.75)
        box(s, LEFT + 4.05, y, 3.0, 0.8, b, fill=CARD, line=None, size=17, font=MONO_FONT)
        y += 1.0
    box(s, LEFT, 5.95, 3.4, 0.8, "Physical tamper", "HMAC report", size=17, sub_size=14)
    box(s, LEFT, 6.95, 3.4, 0.8, "Visual evidence", "ML-DSA-65 signed", size=17, sub_size=14, fill=TINT, line=ORANGE)
    elbow(s, [(LEFT + 3.45, 6.35), (LEFT + 3.75, 6.35), (LEFT + 3.75, 6.85)], arrow=False, lw=1.75)
    elbow(s, [(LEFT + 3.45, 7.35), (LEFT + 3.75, 7.35), (LEFT + 3.75, 6.85), (LEFT + 4.0, 6.85)], lw=1.75)
    box(s, LEFT + 4.05, 6.45, 3.0, 0.8, "Correlation", "within 60 s", size=17, sub_size=14)
    line(s, LEFT + 5.55, 7.29, LEFT + 5.55, 7.85, lw=1.75)
    box(s, LEFT + 4.05, 7.9, 3.0, 0.85, "QUARANTINE", "score 30", fill=ORANGE, line=ORANGE, size=18, sub_size=14, sub_color=INK)
    text(s, LEFT, 9.0, 7.6, 0.95, [[("Real HTTP against the real gateway. Attacks are simulated and labelled; the "
                                     "webcam detections are real.", {"color": MUTED})]], size=15)
    # score path chart
    cx, cy, cw, ch = 9.55, 3.95, 7.4, 4.9
    def ys(v):
        return cy + ch - v / 100 * ch
    box(s, cx, ys(50), cw, ch * 0.5, None, fill=CARD, line=None, kind="rect")
    box(s, cx, ys(80), cw, ch * 0.3, None, fill=TINT, line=None, kind="rect")
    for v in (0, 50, 80):
        text(s, cx - 0.65, ys(v) - 0.2, 0.55, 0.4, str(v), size=14, font=MONO_FONT, align="r", color=MUTED)
    text(s, cx + 0.1, ys(50) + 0.05, 3.0, 0.4, "quarantine", size=14, color=MUTED)
    text(s, cx + 0.1, ys(80) + 0.05, 3.0, 0.4, "suspicious", size=14, color=DEEP)
    pts = [("join", 100), ("webcam", 90), ("forged", 80), ("replay", 72), ("tamper +\nvisual", 30), ("verified", 30),
           ("recovered", 80), ("trusted", 85)]
    step = cw / (len(pts) - 1)
    coords = [(cx + i * step, ys(v)) for i, (_, v) in enumerate(pts)]
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        line(s, x1, y1, x2, y2, color=INK, lw=2.25, arrow=False)
    for (x, y_), (lab, v) in zip(coords, pts):
        hot = v < 50
        node(s, x, y_, r=0.12, fill=ORANGE if hot else WHITE, line=INK, lw=1.5)
        text(s, x - 0.5, y_ - 0.55 if v > 40 else y_ + 0.15, 1.0, 0.4, str(v), size=15, font=MONO_FONT, align="c")
        text(s, x - 0.7, cy + ch + 0.1, 1.4, 0.7, lab, size=13, align="c", color=MUTED, spacing=0.95)
    text(s, cx, 9.65, cw, 0.4, "Live run on the USB webcam, 2026-10-02; recovery shown in announced time-lapse",
         size=14, color=MUTED, align="c")
    notes(s, "Measured, Phase 17 run of scripts/demo_full.py --webcam --pace 2 --hold: 100 -> 90 (real detections of "
             "the presenter in the restricted zone) -> 80 (forged) -> 72 SUSPICIOUS (replay) -> 30 QUARANTINED (tamper + "
             "signed visual) -> VERIFIED 30 -> RECOVERED 80 (30 min credited) -> TRUSTED 85 (42 min). Presentation mode "
             "and a dashboard-against-API check passed on the same run.")
    return s


def s_close(prs, tpl):
    s = blank(prs, tpl.slides[7])
    header(s, S6, "Real-world impact and future scope", "What is still missing, what comes next, and why it matters")
    text(s, LEFT, 3.75, 5.4, 0.5, [[("Honest boundaries", B)]], size=21)
    lim = ["device telemetry simulated; ESP32 never compiled", "device path HMAC-SHA256, not post-quantum",
           "no hardware attestation", "camera thresholds unvalidated; proximity is not a distance",
           "evidence chain not anchored externally", "single gateway; trust parameters uncalibrated"]
    text(s, LEFT, 4.3, 5.4, 4.6, [{"runs": l, "bullet": True, "bullet_color": MUTED} for l in lim], size=17, after=5)
    text(s, 6.65, 3.75, 5.2, 0.5, [[("Next, with hardware", B)]], size=21)
    nxt = ["compile and flash; match the 7 test vectors", "wire the reed switch, then BME280 and MPU6050",
           "stage camera tests: cover, turn, unplug, approach", "measure, then calibrate thresholds",
           "anchor the evidence head externally"]
    y = 4.35
    for i, t in enumerate(nxt, 1):
        box(s, 6.65, y, 0.5, 0.5, str(i), kind="oval", fill=ORANGE if i == 1 else WHITE, line=ORANGE, size=15)
        text(s, 7.3, y - 0.02, 4.6, 0.75, t, size=17, spacing=1.0)
        y += 0.82
    text(s, 12.4, 3.75, 4.7, 0.5, [[("Impact", B)]], size=21)
    text(s, 12.4, 4.3, 4.7, 4.6, [
        {"runs": "labs, server rooms and critical sites get devices that must keep earning trust", "bullet": True},
        {"runs": "incidents arrive with a signed, explainable trail", "bullet": True},
        {"runs": "evidence stays unforgeable into the quantum era", "bullet": True},
    ], size=17, after=8)
    rule(s, LEFT, 8.95, 16.2, color=ORANGE, lw=2.0)
    text(s, LEFT, 9.08, 16.2, 0.85, [[("Authenticate once.  Verify continuously.  Recover only with evidence.", {})]],
         size=30, font=TITLE_FONT, color=INK, align="c")
    notes(s, "Close on the line at the bottom. Limitations are listed in README.md and docs/IMPLEMENTATION_STATUS.md; "
             "the hardware path is docs/hardware/hardware-architecture.md section 2.")
    return s


SLIDES = [s_participant, s_problem, s_threats, s_requirements, s_loop, s_architecture, s_factors, s_scoring,
          s_crypto, s_handshake, s_signed, s_abuse, s_vision, s_camera, s_twin, s_chain, s_enforce, s_recovery,
          s_stack, s_feasible, s_perf, s_usp, s_results, s_close]


def main() -> int:
    prs = Presentation(str(TEMPLATE))
    n_template = len(prs.slides)
    made = []
    for fn in SLIDES:
        made.append(fn(prs, prs))
    drop_slides(prs, n_template)
    for i, s in enumerate(made, 1):
        footer(s, i, len(made))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"wrote {OUT} ({len(made)} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
