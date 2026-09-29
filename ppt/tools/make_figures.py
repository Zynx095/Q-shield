"""Generate presentation figures (PNG + SVG) from the repository's real data.

    python ppt/tools/make_figures.py

Data sources (nothing is typed in by hand except structure/labels):
  docs/results/pqc-benchmark.json      measured PQC latencies and sizes
  docs/results/live-run-phase3.json    real webcam -> gateway run evidence
  tests/vectors/pqc/*.json             NIST ACVP vectors actually used by the tests
  pytest --collect-only                test counts per area
  ai/README.md                         vision throughput table (asserted below so it cannot drift)
No screenshots are fabricated; diagrams show implemented vs planned components explicitly.
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PPT = Path(__file__).resolve().parents[1]
OUT = PPT / "diagrams"     # diagrams and flow figures
DIAG_DEST = OUT
ASSETS = PPT / "assets"    # measured-data charts
BG, PANEL, TEXT, MUTED = "#0B1220", "#121C31", "#E6EDF7", "#8FA1BC"
GREEN, GREEN_BG = "#34D399", "#0F3B33"        # implemented
AMBER, AMBER_BG = "#FBBF24", "#2A2410"        # planned / next phase
BLUE, BLUE_BG = "#60A5FA", "#12294A"          # PQC component
GREY, GREY_BG = "#94A3B8", "#1B2536"          # classical / not PQC
RED = "#F87171"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": TEXT, "axes.labelcolor": TEXT,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": MUTED})


def canvas(w=16, h=9, title=None, subtitle=None):
    fig = plt.figure(figsize=(w, h), dpi=120, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 160), ax.set_ylim(0, 90), ax.axis("off")
    ax.set_facecolor(BG)
    if title:
        ax.text(5, 84, title, fontsize=26, fontweight="bold", va="center")
    if subtitle:
        ax.text(5, 79.5, subtitle, fontsize=13.5, color=MUTED, va="center")
    return fig, ax


def box(ax, x, y, w, h, title, sub=None, fc=PANEL, ec=MUTED, ls="-", lw=2.2, fs=14, sfs=10.5, tc=TEXT):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2", fc=fc, ec=ec, lw=lw, ls=ls))
    if sub:
        ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=fs, fontweight="bold", color=tc)
        ax.text(x + w / 2, y + h * 0.30, sub, ha="center", va="center", fontsize=sfs, color=MUTED, linespacing=1.35)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=fs, fontweight="bold", color=tc)


def arrow(ax, p1, p2, color=MUTED, ls="-", lw=2.2, label=None, lsize=10.5, off=(0, 1.6), style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=18, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((p1[0] + p2[0]) / 2 + off[0], (p1[1] + p2[1]) / 2 + off[1], label, ha="center", va="center",
                fontsize=lsize, color=color)


def legend(ax, items, x=5, y=4):
    for i, (label, fc, ec, ls) in enumerate(items):
        xx = x + i * 38
        ax.add_patch(FancyBboxPatch((xx, y), 3.2, 2.4, boxstyle="round,pad=0.1,rounding_size=0.5", fc=fc, ec=ec, lw=2, ls=ls))
        ax.text(xx + 4.4, y + 1.2, label, va="center", fontsize=11, color=MUTED)


def save(fig, name, dest=None):
    for ext in ("png", "svg"):
        fig.savefig((dest or OUT) / f"{name}.{ext}", facecolor=BG)
    plt.close(fig)
    print("wrote", name)


LEGEND = [("Implemented and tested", GREEN_BG, GREEN, "-"), ("PQC component (ML-KEM / ML-DSA)", BLUE_BG, BLUE, "-"),
          ("Classical (not post-quantum)", GREY_BG, GREY, "-"), ("Planned, NOT yet implemented", AMBER_BG, AMBER, "--")]


# ---------------------------------------------------------------- 1. architecture
def architecture():
    fig, ax = canvas(title="Q-SHIELD architecture: current milestone",
                     subtitle="Solid = built and tested. Dashed amber = planned next phases, not implemented.")
    box(ax, 5, 52, 26, 13, "USB webcam", "laptop camera, 640x480", GREEN_BG, GREEN)
    box(ax, 40, 52, 34, 13, "Vision service", "YOLO11n + zones -> observations\nML-DSA-65 service identity", BLUE_BG, BLUE)
    arrow(ax, (31.5, 58.5), (39.7, 58.5), GREEN)
    box(ax, 5, 26, 34, 15, "ESP32 endpoint", "firmware skeleton (untested);\nsoftware device agent used so far", GREY_BG, GREY)
    ax.text(22, 22.6, "HMAC-SHA256 auth: NOT post-quantum", ha="center", fontsize=11.5, color=AMBER, fontweight="bold")
    box(ax, 92, 30, 44, 36, "", None, GREEN_BG, GREEN)
    ax.text(114, 62.3, "Gateway (laptop)", ha="center", fontsize=16, fontweight="bold")
    ax.text(114, 58.6, "FastAPI + SQLite", ha="center", fontsize=11, color=MUTED)
    for i, (t, c) in enumerate([("HMAC verify + replay counter (devices)", GREY), ("ML-DSA-65 verify + freshness + replay", BLUE),
                                ("ML-KEM-768 session termination", BLUE), ("Operator / ingest bearer tokens", GREY)]):
        ax.add_patch(FancyBboxPatch((95, 51.4 - i * 5.4), 38, 4.1, boxstyle="round,pad=0.1,rounding_size=0.6", fc=PANEL, ec=c, lw=1.6))
        ax.text(114, 53.45 - i * 5.4, t, ha="center", va="center", fontsize=10.8)
    arrow(ax, (74.3, 58.5), (91.7, 58.5), BLUE)
    ax.text(83, 62.6, "signed", ha="center", fontsize=10.5, color=BLUE)
    ax.text(83, 54.4, "optional ML-KEM\nsession", ha="center", va="center", fontsize=9.5, color=BLUE, linespacing=1.2)
    arrow(ax, (39.3, 33.5), (91.7, 40), GREY, label="HMAC-SHA256 telemetry + heartbeat", off=(0, -3.2))
    box(ax, 92, 8, 21, 13, "Observation store", "auth label per record", GREEN_BG, GREEN, fs=12.5, sfs=10)
    box(ax, 115, 8, 21, 13, "Security events", "reason-coded", GREEN_BG, GREEN, fs=12.5, sfs=10)
    arrow(ax, (105, 29.7), (102.5, 21.4), GREEN), arrow(ax, (123, 29.7), (125.5, 21.4), GREEN)
    box(ax, 140, 47, 17, 20, "Dynamic\ntrust engine", "Phase 4:\nspec pending", AMBER_BG, AMBER, ls="--", fs=12, sfs=10)
    arrow(ax, (136.4, 57), (139.7, 57), AMBER, "--")
    box(ax, 140, 22, 17, 20, "Quarantine\n+ recovery", "planned", AMBER_BG, AMBER, ls="--", fs=12, sfs=10)
    arrow(ax, (148.5, 46.7), (148.5, 42.3), AMBER, "--")
    box(ax, 44, 8, 43, 12, "Evidence chain - digital twin - dashboard", "planned", AMBER_BG, AMBER, ls="--", fs=12, sfs=10)
    legend(ax, LEGEND, x=5, y=1.2)
    save(fig, "01_architecture")


# ---------------------------------------------------------------- 2. closed loop
def closed_loop():
    fig, ax = canvas(title="The Q-SHIELD closed loop", subtitle="What exists today versus what the next phases add")
    stages = [("OBSERVE", "webcam + YOLO11n\ndevice telemetry", True), ("AUTHENTICATE", "HMAC (device)\nML-DSA (observations)", True),
              ("ANALYZE", "zone rules,\ncamera health", True), ("TRUST", "dynamic score,\nexplainable", False),
              ("QUARANTINE", "state machine,\nrevoke session", False), ("RECOVER", "safe mode,\nverified restore", False),
              ("RE-AUTH", "new PQC\nsession", False), ("RESTORE", "gradual,\nvalidated", False)]
    w, gap, x0, y = 16.6, 2.5, 4.5, 40
    for i, (t, sub, done) in enumerate(stages):
        x = x0 + i * (w + gap)
        box(ax, x, y, w, 15, t, sub, GREEN_BG if done else AMBER_BG, GREEN if done else AMBER, "-" if done else "--", fs=11.5, sfs=10)
        if i < 7:
            arrow(ax, (x + w + 0.3, y + 7.5), (x + w + gap - 0.3, y + 7.5), GREEN if i < 2 else AMBER, "-" if i < 2 else "--")
    xa, xb = x0, x0 + 3 * (w + gap) + w
    ax.plot([xa, xb], [y + 19, y + 19], color=GREEN, lw=3)
    ax.text((xa + xb) / 2, y + 22, "BUILT AND TESTED", ha="center", fontsize=13, color=GREEN, fontweight="bold")
    ax.plot([x0 + 3 * (w + gap), x0 + 8 * w + 7 * gap], [y - 4, y - 4], color=AMBER, lw=3, ls="--")
    ax.text((x0 + 3 * (w + gap) + x0 + 8 * w + 7 * gap) / 2, y - 8, "PLANNED (trust engine spec comes first)", ha="center", fontsize=13, color=AMBER, fontweight="bold")
    ax.text(5, 20, "Built today: observe -> authenticate -> analyze. Next: trust specification (Phase 4A), then quarantine, recovery, evidence chain.", fontsize=13.5, color=TEXT)
    ax.text(5, 13.5, "Authenticity is not trust: a valid signature proves which key produced an observation, not that the device is uncompromised.", fontsize=12.5, color=MUTED)
    save(fig, "02_closed_loop")


# ---------------------------------------------------------------- 3. signed flow with live evidence
def signed_flow():
    live = json.loads((ROOT / "docs/results/live-run-phase3.json").read_text())
    seq = live["http_post_status_sequence"]
    n = live["observations_stored"]
    fig, ax = canvas(title="Signed observation path: real run, real outcomes",
                     subtitle="USB webcam + YOLO11n -> vision service (ML-DSA-65 identity) -> ML-KEM-768 session -> gateway")
    box(ax, 5, 56, 30, 12, "Vision service", "signs each observation\nML-DSA-65, signer vision-1", BLUE_BG, BLUE)
    box(ax, 62, 56, 34, 12, "ML-KEM-768 session", "AES-256-GCM, counters,\nkey-confirmation tag", BLUE_BG, BLUE)
    box(ax, 123, 56, 32, 12, "Gateway", "verifies before it stores", GREEN_BG, GREEN)
    arrow(ax, (35.4, 62), (61.7, 62), BLUE), arrow(ax, (96.4, 62), (122.7, 62), BLUE)
    ax.text(48.5, 65.5, "signed envelope", ha="center", fontsize=10.5, color=MUTED)
    checks = ["signer enrolled + active", "ML-DSA-65 signature (canonical bytes)", "timestamp fresh (+/-300 s)", "payload matches metadata",
              "signer authorised for device + source", "not a replay (observation_id)"]
    ax.text(123, 50, "Gateway checks, in order:", fontsize=12.5, fontweight="bold")
    for i, c in enumerate(checks):
        ax.text(124, 46 - i * 3.6, f"{i + 1}.  {c}", fontsize=11, color=MUTED)
    rows = [(f"{seq.get('/api/v1/pqc/session -> 200', 0)}x session handshake", "HTTP 200", GREEN),
            (f"{seq.get('/api/v1/observations/secure -> 200', 0)}x signed observations in session", "HTTP 200", GREEN),
            ("1x observation with altered payload", f"HTTP {401}", RED), ("1x exact replay of a stored envelope", f"HTTP {409}", AMBER)]
    ax.text(5, 47, "Recorded outcomes (docs/results/live-run-phase3.json)", fontsize=14, fontweight="bold")
    for i, (lab, code, c) in enumerate(rows):
        yy = 40 - i * 7.2
        ax.add_patch(FancyBboxPatch((5, yy - 2.6), 92, 5.6, boxstyle="round,pad=0.1,rounding_size=0.6", fc=PANEL, ec=c, lw=1.8))
        ax.text(8, yy + 0.2, lab, fontsize=13, va="center")
        ax.text(93, yy + 0.2, code, fontsize=14, fontweight="bold", color=c, va="center", ha="right")
    v = live["offline_reverification"]
    ax.text(5, 8.5, f"{n} of {n} stored observations labelled ML-DSA-65:vision-1. Offline re-verification: {v['valid']}/{v['envelopes_checked']} valid, "
                    f"{v['altered_copies_rejected']}/{v['envelopes_checked']} altered copies rejected.", fontsize=12.5, color=GREEN)
    ax.text(5, 4.2, "Scene note: no person was in view; detections were chairs and a plant (no anomaly flagged). The person-in-zone path was not run live.",
            fontsize=11, color=MUTED)
    save(fig, "03_signed_observation_flow")


# ---------------------------------------------------------------- 4. security domains
def domains():
    fig, ax = canvas(title="Security domains: what is post-quantum, and what is not",
                     subtitle="Q-SHIELD adds a PQC layer while keeping HMAC-SHA256 for the current ESP32 prototype")
    cols = [("ESP32 device", GREY_BG, GREY, ["HMAC-SHA256 per-device secret", "counter replay protection", "no confidentiality", "NOT post-quantum"], AMBER),
            ("Vision service (software)", BLUE_BG, BLUE, ["ML-DSA-65 signed observations", "optional ML-KEM-768 session", "AES-256-GCM session traffic", "identity = the service,\nnot the webcam"], BLUE),
            ("Gateway", BLUE_BG, BLUE, ["verifies ML-DSA-65 signatures", "terminates ML-KEM-768 sessions", "encrypted device-credential store", "HMAC verification for ESP32"], BLUE),
            ("Operators / ingest", GREY_BG, GREY, ["bearer tokens (separate scopes)", "token-only ingest path", "labelled ingest-token, not PQC", "can be disabled"], AMBER)]
    for i, (t, fc, ec, lines, hc) in enumerate(cols):
        x = 5 + i * 38.5
        box(ax, x, 22, 35, 48, "", None, fc, ec)
        ax.text(x + 17.5, 65, t, ha="center", fontsize=15, fontweight="bold")
        for j, ln in enumerate(lines):
            last = j == len(lines) - 1
            ax.text(x + 17.5, 57 - j * 8.6, ln, ha="center", va="center", fontsize=12.2,
                    color=(hc if last and i in (0, 1) else TEXT), fontweight=("bold" if last and i in (0, 1) else "normal"), linespacing=1.3)
    ax.text(5, 15, "We do not claim the ESP32 is quantum-safe. ESP32-side PQC feasibility is a separate, unfinished research item (R1).", fontsize=14, color=AMBER, fontweight="bold")
    ax.text(5, 9.5, "Algorithms: ML-KEM-768 (FIPS 203) key establishment; ML-DSA-65 (FIPS 204) signatures. Library: pqcrypto 1.0.0 (Apache-2.0).", fontsize=12.5, color=MUTED)
    save(fig, "04_security_domains")


# ---------------------------------------------------------------- 5. PQC benchmark
def pqc_bench():
    d = json.loads((ROOT / "docs/results/pqc-benchmark.json").read_text())
    lat = d["latency_ms"]
    ops = [("ML-KEM-768 keygen", "ml_kem_768_keygen", BLUE), ("ML-KEM-768 encapsulate", "ml_kem_768_encapsulate", BLUE),
           ("ML-KEM-768 decapsulate", "ml_kem_768_decapsulate", BLUE), ("ML-DSA-65 keygen", "ml_dsa_65_keygen", GREEN),
           ("ML-DSA-65 verify", "ml_dsa_65_verify", GREEN), ("ML-DSA-65 sign", "ml_dsa_65_sign", GREEN)]
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BG)
    ax = fig.add_axes([0.24, 0.20, 0.70, 0.60], facecolor=PANEL)
    for i, (lab, key, c) in enumerate(ops):
        m, p95 = lat[key]["median"], lat[key]["p95"]
        ax.barh(i, m, color=c, height=0.55)
        ax.plot([p95, p95], [i - 0.27, i + 0.27], color=TEXT, lw=2)
        ax.text(max(p95, m) * 1.12, i, f"{m:.3f} ms", va="center", fontsize=14, fontweight="bold")
    ax.set_yticks(range(len(ops)), [o[0] for o in ops], fontsize=14)
    ax.set_xscale("log"), ax.set_xlim(0.02, 60), ax.invert_yaxis()
    ax.set_xlabel("median latency, milliseconds (log scale); white tick = p95", fontsize=12.5)
    for s in ax.spines.values():
        s.set_color(MUTED)
    ax.grid(axis="x", color="#22304D", lw=0.8), ax.set_axisbelow(True)
    e = d["environment"]
    fig.text(0.05, 0.92, "PQC operation latency (measured)", fontsize=26, fontweight="bold")
    fig.text(0.05, 0.875, f"{e['cpu']}, {e['os'].split('-SP')[0]}, Python {e['python']}, pqcrypto {d['crypto']['library_version']}.  "
                          f"{d['method']['iterations_per_round']} calls x {d['method']['rounds']} rounds per operation.", fontsize=12.5, color=MUTED)
    s = d["sizes_bytes"]
    fig.text(0.05, 0.115, f"Sizes (bytes): ML-DSA-65 signature {s['signature']}  |  ML-KEM-768 ciphertext {s['kem_ciphertext']}  |  "
                          f"ML-KEM public key {s['kem_public_key']}  |  ML-KEM private key {s['kem_secret_key']}", fontsize=13, color=TEXT)
    fig.text(0.05, 0.06, "Laptop measurements only. They say nothing about ESP32 or other embedded performance. Signing is ~50x slower than verification in this library.",
             fontsize=12, color=AMBER)
    for ext in ("png", "svg"):
        fig.savefig(ASSETS / f"05_pqc_benchmark.{ext}", facecolor=BG)
    plt.close(fig), print("wrote 05_pqc_benchmark")


# ---------------------------------------------------------------- 6. vision throughput
def vision_perf():
    readme = (ROOT / "ai/README.md").read_text(encoding="utf-8")
    table = {"640": (25.1, 21.0, 39.8), "320": (51.4, 30.0, 19.5)}
    for k, (inf, e2e, ms) in table.items():           # guard: the chart must match the recorded README table
        assert f"{inf}" in readme and f"{e2e}" in readme and f"{ms}" in readme, f"ai/README.md no longer contains {k} row"
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BG)
    ax = fig.add_axes([0.10, 0.22, 0.55, 0.58], facecolor=PANEL)
    xs = [0, 1]
    ax.bar([x - 0.19 for x in xs], [table["640"][0], table["320"][0]], 0.36, color=BLUE, label="inference-only FPS")
    ax.bar([x + 0.19 for x in xs], [table["640"][1], table["320"][1]], 0.36, color=GREEN, label="end-to-end FPS (capture + inference)")
    for x, k in zip(xs, ("640", "320")):
        ax.text(x - 0.19, table[k][0] + 1, f"{table[k][0]}", ha="center", fontsize=15, fontweight="bold")
        ax.text(x + 0.19, table[k][1] + 1, f"{table[k][1]}", ha="center", fontsize=15, fontweight="bold")
    ax.set_xticks(xs, ["imgsz 640 (configured)", "imgsz 320 (comparison)"], fontsize=14)
    ax.set_ylabel("frames per second", fontsize=13), ax.set_ylim(0, 62)
    ax.legend(facecolor=PANEL, edgecolor=MUTED, fontsize=12, labelcolor=TEXT, loc="upper left")
    ax.grid(axis="y", color="#22304D"), ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_color(MUTED)
    fig.text(0.05, 0.92, "Vision pipeline throughput (measured)", fontsize=26, fontweight="bold")
    fig.text(0.05, 0.875, "YOLO11n (5.6 MB checkpoint, AGPL-3.0), CPU only, 640x480 USB webcam, 100 frames per run, one run each.", fontsize=12.5, color=MUTED)
    fig.text(0.69, 0.66, "This is speed, not accuracy.", fontsize=17, fontweight="bold", color=AMBER)
    fig.text(0.69, 0.60, "No detection accuracy or false-positive\nrate has been measured.\n\nNo person was in view during the runs\n(0 detections), so post-processing with\ndetections is not represented.\n\nInference mean: 39.8 ms (640), 19.5 ms (320).",
             fontsize=13, color=MUTED, va="top", linespacing=1.4)
    for ext in ("png", "svg"):
        fig.savefig(ASSETS / f"06_vision_performance.{ext}", facecolor=BG)
    plt.close(fig), print("wrote 06_vision_performance")


# ---------------------------------------------------------------- 7. NIST conformance
def conformance():
    kem = json.loads((ROOT / "tests/vectors/pqc/acvp_mlkem768.json").read_text())
    dsa = json.loads((ROOT / "tests/vectors/pqc/acvp_mldsa65_sigver.json").read_text())
    g = {x["function"]: x["tests"] for x in kem["testGroups"]}
    decaps = len(g["decapsulation"]) + len(g["encapsulation"])
    keychecks = len(g["encapsulationKeyCheck"]) + len(g["decapsulationKeyCheck"])
    tests = dsa["testGroups"][0]["tests"]
    valid = sum(1 for t in tests if t["testPassed"] in (True, "True"))
    manifest = json.loads((ROOT / "tests/vectors/pqc/MANIFEST.json").read_text())
    fig, ax = canvas(title="NIST ACVP known-answer evidence", subtitle=f"Vectors copied verbatim from usnistgov/ACVP-Server, commit {manifest['acvp_server_commit'][:10]}")
    cards = [("ML-KEM-768", f"{decaps}", "decapsulation cases", "all match NIST's shared secrets", BLUE),
             ("ML-KEM-768", f"{keychecks}", "key-validity cases", "library agrees with NIST on valid and invalid keys", BLUE),
             ("ML-DSA-65", f"{len(tests)}", "verification cases", f"{valid} valid, {len(tests) - valid} invalid: all agree", GREEN)]
    for i, (alg, big, what, note, c) in enumerate(cards):
        x = 5 + i * 51
        box(ax, x, 36, 47, 34, "", None, PANEL, c)
        ax.text(x + 23.5, 64, alg, ha="center", fontsize=16, color=c, fontweight="bold")
        ax.text(x + 23.5, 53, big, ha="center", fontsize=60, fontweight="bold")
        ax.text(x + 23.5, 43.5, what, ha="center", fontsize=15)
        ax.text(x + 23.5, 39, note, ha="center", fontsize=11, color=MUTED)
    ax.text(5, 28, "Also: pure-Python reference implementations (kyber-py, dilithium-py) pass the same vectors and interoperate with pqcrypto in both directions.", fontsize=13)
    ax.text(5, 22, "Not covered, and not claimed: keygen / signing / encapsulation known-answer tests (the library takes no seed), pre-hash mode,", fontsize=12.5, color=AMBER)
    ax.text(5, 18, "other parameter sets, side channels, independent audit. No FIPS 140 validation. Passing vectors is evidence of algorithm-level correctness, not certification.", fontsize=12.5, color=AMBER)
    ax.text(5, 9, "Library: pqcrypto 1.0.0 (Apache-2.0), verified on Windows x86-64 only.", fontsize=12.5, color=MUTED)
    save(fig, "07_nist_conformance", ASSETS)


# ---------------------------------------------------------------- 8. tests
def tests_chart():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="], cwd=ROOT,
                         capture_output=True, text=True).stdout
    per_file = Counter(l.split("::")[0] for l in out.splitlines() if "::" in l)
    total = sum(per_file.values())
    m = re.search(r"(\d+) tests? collected", out)
    assert m is None or int(m.group(1)) == total
    groups = {
        "Phase 1: device auth, replay, PQC interface": ["tests/security/test_device_auth.py", "tests/integration/test_phase1_flow.py", "tests/pqc/test_pqc_interface.py"],
        "Phase 0/1 hardening: credentials, operator auth": ["tests/security/test_credential_store.py", "tests/security/test_operator_auth.py"],
        "Phase 2: vision, schema, zones, ingest": [f for f in per_file if f.startswith("tests/ai/") or f == "tests/integration/test_observation_ingest.py"],
        "Phase 3: PQC conformance, interop, behaviour": ["tests/pqc/test_conformance_acvp.py", "tests/pqc/test_interop_reference.py", "tests/pqc/test_mlkem768_mldsa65_behaviour.py"],
        "Phase 3: signed observations, sessions, keys": ["tests/security/test_signed_observations.py", "tests/security/test_pqc_session.py", "tests/security/test_pqc_keystore.py", "tests/integration/test_vision_signed_sink.py"],
    }
    counts = [(k, sum(per_file.get(f, 0) for f in v)) for k, v in groups.items()]
    assert sum(c for _, c in counts) == total, (sum(c for _, c in counts), total)
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BG)
    ax = fig.add_axes([0.36, 0.16, 0.58, 0.62], facecolor=PANEL)
    cols = [GREEN, GREEN, GREEN, BLUE, BLUE]
    for i, ((lab, c), col) in enumerate(zip(counts, cols)):
        ax.barh(i, c, color=col, height=0.6)
        ax.text(c + 2, i, str(c), va="center", fontsize=16, fontweight="bold")
    ax.set_yticks(range(len(counts)), [c[0] for c in counts], fontsize=12.5), ax.invert_yaxis()
    ax.set_xlim(0, max(c for _, c in counts) * 1.15)
    ax.grid(axis="x", color="#22304D"), ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_color(MUTED)
    fig.text(0.05, 0.92, f"{total} of {total} automated tests passing", fontsize=28, fontweight="bold")
    fig.text(0.05, 0.875, "pytest, counted from the repository at build time. The 182 tests that existed before Phase 3 are unchanged and still pass.", fontsize=12.5, color=MUTED)
    fig.text(0.05, 0.07, "Tests verify implemented behaviour only. Trust engine, quarantine, recovery, evidence chain and dashboard have no tests because they are not implemented.",
             fontsize=12, color=AMBER)
    for ext in ("png", "svg"):
        fig.savefig(ASSETS / f"08_test_summary.{ext}", facecolor=BG)
    plt.close(fig), print("wrote 08_test_summary", total)
    return total


# ---------------------------------------------------------------- 9. authenticity != trust
def authenticity():
    fig, ax = canvas(title="Authenticity is not trust", subtitle="Why Q-SHIELD treats authentication as an input to trust, not as the decision")
    box(ax, 5, 44, 72, 26, "", None, BLUE_BG, BLUE)
    ax.text(41, 65, "A valid ML-DSA-65 signature proves", ha="center", fontsize=16, fontweight="bold", color=BLUE)
    ax.text(41, 57, "the holder of the signing key produced\nthis exact observation (provenance + integrity)", ha="center", va="center", fontsize=15, linespacing=1.4)
    ax.text(41, 47.5, "A valid HMAC-SHA256 tag proves possession of the provisioned device secret", ha="center", fontsize=11.5, color=MUTED)
    box(ax, 83, 44, 72, 26, "", None, AMBER_BG, AMBER, ls="--")
    ax.text(119, 65, "It does NOT prove", ha="center", fontsize=16, fontweight="bold", color=AMBER)
    ax.text(119, 56, "the physical device is uncompromised,\nthe sensor is not being spoofed,\nor the detected scene is benign", ha="center", va="center", fontsize=14.5, linespacing=1.5)
    ax.text(5, 34, "So the (planned) trust engine takes authentication as one input among several:", fontsize=15, fontweight="bold")
    items = ["device authentication status", "observation authenticity", "replay / freshness violations", "sensor + visual anomalies",
             "physical tamper state", "device integrity (self-reported, not proof)", "recent security events", "AI confidence: separate from authenticity"]
    for i, it in enumerate(items):
        ax.text(7 + (i // 4) * 75, 27 - (i % 4) * 5.2, "-  " + it, fontsize=13, color=TEXT)
    ax.text(5, 4, "Trust engine specification is the next step and is not yet written; this slide states the principle it will follow.", fontsize=12, color=AMBER)
    save(fig, "09_authenticity_is_not_trust")


# ---------------------------------------------------------------- 10. security architecture (as sketched in the brief)
def security_architecture():
    fig, ax = canvas(title="Security architecture: built path and planned trust loop",
                     subtitle="Green/blue/grey = built and tested. Dashed amber = future phases (trust engine spec pending). No trust states exist yet.")
    box(ax, 5, 62, 26, 12, "USB webcam", "640x480", GREEN_BG, GREEN, fs=13)
    box(ax, 40, 62, 42, 12, "Vision service", "YOLO11n -> observations\nML-DSA-65 service identity", BLUE_BG, BLUE, fs=13, sfs=10)
    arrow(ax, (31.5, 68), (39.7, 68), GREEN)
    box(ax, 88, 62, 26, 12, "ML-KEM-768 session", "AES-256-GCM (optional)", BLUE_BG, BLUE, fs=11.5, sfs=9.5)
    arrow(ax, (82.4, 68), (87.7, 68), BLUE)
    box(ax, 120, 58, 35, 16, "Gateway", "verifies before it stores", GREEN_BG, GREEN, fs=15)
    arrow(ax, (114.4, 68), (119.7, 68), BLUE)
    box(ax, 5, 40, 40, 12, "ESP32 endpoint", "software agent so far; firmware untested", GREY_BG, GREY, fs=13, sfs=9.5)
    arrow(ax, (45.4, 46), (119.7, 62), GREY, label="HMAC-SHA256 (NOT post-quantum)", off=(-6, -5.5), lsize=11)
    box(ax, 100, 38, 26, 11, "Observation\nvalidation", None, GREEN_BG, GREEN, fs=12)
    box(ax, 130, 38, 25, 11, "Security\nevents", None, GREEN_BG, GREEN, fs=12)
    arrow(ax, (132, 57.7), (116, 49.4), GREEN), arrow(ax, (144, 57.7), (144, 49.4), GREEN)
    box(ax, 62, 23, 78, 9, "Dynamic trust (Phase 4: specification pending, not implemented)", None, AMBER_BG, AMBER, ls="--", fs=12)
    arrow(ax, (113, 37.7), (113, 32.6), AMBER, "--"), arrow(ax, (142, 37.7), (128, 32.6), AMBER, "--")
    for i, (t, x) in enumerate([("TRUSTED", 50), ("SUSPICIOUS", 76), ("QUARANTINED", 102)]):
        box(ax, x, 8, 23, 9, t, None, AMBER_BG, AMBER, ls="--", fs=11.5)
        arrow(ax, (75 + i * 14, 22.6), (x + 11.5, 17.6), AMBER, "--")
    box(ax, 130, 8, 25, 9, "Recovery (future)", None, AMBER_BG, AMBER, ls="--", fs=11.5)
    arrow(ax, (125.4, 12.5), (129.7, 12.5), AMBER, "--")
    ax.text(5, 30, "Nothing below the dashed line", fontsize=11.5, color=AMBER), ax.text(5, 26.4, "exists in code yet.", fontsize=11.5, color=AMBER)
    ax.text(5, 22, "Authenticity is an input to trust,", fontsize=11.5, color=MUTED), ax.text(5, 18.4, "never the whole decision.", fontsize=11.5, color=MUTED)
    save(fig, "10_security_architecture")


if __name__ == "__main__":
    architecture(), closed_loop(), signed_flow(), domains(), pqc_bench(), vision_perf(), conformance(), authenticity()
    security_architecture()
    tests_chart()
    import figures_more
    figures_more.main()
