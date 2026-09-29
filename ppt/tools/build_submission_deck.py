"""Build the official-template idea submission deck (6 slides) by filling a COPY of the official sample.

    python ppt/tools/build_submission_deck.py [--template "<path to PPT SAMPLE.pptx>"]

The original template is opened read-only and is never modified. The output is
ppt/Q-SHIELD_idea_submission.pptx. Preserved from the template: slide size (13.333 x 7.5 in), background,
logos, header/footer bars, slide numbers, every section heading, layout and fonts. Changed: the body text of
each field, the diagram frame on slide 3 (a picture replaces the placeholder text) and the removal of the
last slide ("How to use this template"), as its own note instructs.

Fields the team must supply are left as [BRACKETED] placeholders (team name, members, school, contact,
problem statement number, track). No team details from the sample are carried over.
"""
import argparse
import copy
import hashlib
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deck_content import SUBMISSION_REFS  # noqa: E402

DEFAULT_TEMPLATE = ROOT.parent / "shadowguard-main" / "PPT SAMPLE.pptx"
TEAM = "[TEAM NAME]"


def shape(slide, name, nth=0):
    hits = [s for s in slide.shapes if s.name == name]
    if len(hits) <= nth:
        raise KeyError(f"{name!r} not found on slide")
    return hits[nth]


def set_paras(shp, lines):
    """Replace the paragraphs of a text shape, cloning the first paragraph so bullets, fonts and colours stay as in the template."""
    tx = shp.text_frame._txBody
    paras = tx.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}p")
    proto = copy.deepcopy(paras[0])
    for p in paras:
        tx.remove(p)
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    for line in lines:
        p = copy.deepcopy(proto)
        runs = p.findall(ns + "r")
        for extra in runs[1:]:
            p.remove(extra)
        if runs:
            runs[0].find(ns + "t").text = line
        else:  # prototype had no run: add one
            raise ValueError("template paragraph without a run")
        tx.append(p)


def restyle(shp, size_pt, color="E9F1FA", font="Calibri", bold=False):
    """Give a value box the template's own field look (some sample boxes carry another author's fonts)."""
    from pptx.dml.color import RGBColor
    from pptx.util import Pt
    for p in shp.text_frame.paragraphs:
        for r in p.runs:
            r.font.name, r.font.size, r.font.bold = font, Pt(size_pt), bold
            r.font.color.rgb = RGBColor.from_string(color)


def clone_run_format(src, dst):
    """Copy the first run's formatting from one shape to another (same template style)."""
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    s_r = src.text_frame._txBody.find(ns + "p").find(ns + "r")
    d_r = dst.text_frame._txBody.find(ns + "p").find(ns + "r")
    d_old = d_r.find(ns + "rPr")
    if d_old is not None:
        d_r.remove(d_old)
    d_r.insert(0, copy.deepcopy(s_r.find(ns + "rPr")))


def delete_slide(prs, index):
    sldIdLst = prs.slides._sldIdLst
    sld = sldIdLst[index]
    prs.part.drop_rel(sld.rId)
    sldIdLst.remove(sld)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--team-name", default="[TEAM NAME]")
    ap.add_argument("--members", default="[TEAM MEMBERS]", help="e.g. \"A, B, C\" (4 max)")
    ap.add_argument("--school", default="[SCHOOL]")
    ap.add_argument("--contact", default="[CONTACT]", help="team leader contact")
    ap.add_argument("--ps-number", default="[NO.]", help="problem statement number")
    ap.add_argument("--track", default="[TRACK / THEME]")
    ap.add_argument("--title", default="Q-SHIELD: QUANTUM-RESILIENT AIoT SECURITY", help="problem statement / idea title (one line)")
    ap.add_argument("--out", default=str(ROOT / "ppt" / "Q-SHIELD_idea_submission.pptx"))
    a = ap.parse_args()
    TEAM = a.team_name  # local name shadows the module placeholder
    tpl = Path(a.template)
    if not tpl.is_file():
        print(f"official template not found: {tpl}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(tpl.read_bytes()).hexdigest()
    prs = Presentation(str(tpl))          # read into memory; saved to a different file below
    s = list(prs.slides)
    assert len(s) == 7, "unexpected template: expected 7 slides"

    # ---- slide 1: title slide fields
    s1 = s[0]
    set_paras(shape(s1, "TextBox 27"), [a.ps_number])
    set_paras(shape(s1, "TextBox 31"), [a.title.upper()])
    set_paras(shape(s1, "TextBox 32"), [a.track])
    set_paras(shape(s1, "TextBox 9"), [TEAM])
    set_paras(shape(s1, "TextBox 11"), [a.members])
    set_paras(shape(s1, "TextBox 24"), [a.school])
    set_paras(shape(s1, "TextBox 29"), [a.contact])
    for nm, sz in (("TextBox 27", 16), ("TextBox 31", 13), ("TextBox 32", 14), ("TextBox 9", 15), ("TextBox 11", 14), ("TextBox 24", 14), ("TextBox 29", 14)):
        restyle(shape(s1, nm), sz)

    # ---- slide 2: idea
    s2 = s[1]
    clone_run_format(shape(s[2], "Text 1"), shape(s2, "Text 1"))
    set_paras(shape(s2, "Text 1"), [TEAM])
    set_paras(shape(s2, "Text 6"), ["Q-SHIELD: CONTINUOUS TRUST FOR AIoT, WITH A POST-QUANTUM LAYER"])
    set_paras(shape(s2, "Text 12"), ["Continuous trust, not one-time authentication (planned)", "Cyber + visual signals now, physical next",
                                     "Post-quantum layer: ML-KEM-768 + ML-DSA-65"])
    set_paras(shape(s2, "Text 17"), ["Webcam + YOLO11n produce signed observations", "Modified, forged or replayed messages are rejected and logged",
                                     "Trust engine (next) turns evidence into explainable trust"])
    set_paras(shape(s2, "Text 22"), ["Proposed integration, not a new algorithm", "Authenticity is an input to trust, never the decision",
                                     "Built parts tested: 347/347 tests, NIST vectors"])
    set_paras(shape(s2, "Text 24"), ["BUILT: Phases 0-3, 347/347 tests   |   NEXT: trust engine, quarantine, recovery   |   ESP32 uses HMAC-SHA256 (not post-quantum)"])

    # ---- slide 3: technical approach
    s3 = s[2]
    set_paras(shape(s3, "Text 1"), [TEAM])
    set_paras(shape(s3, "Text 9"), ["Python, FastAPI, SQLite; YOLO11n webcam", "ML-KEM-768, ML-DSA-65, AES-256-GCM",
                                    "ESP32: HMAC-SHA256, firmware unvalidated"])
    set_paras(shape(s3, "Text 13"), ["Vertical slices: device, vision, PQC, then trust", "Observations first; trust decisions later",
                                     "Validate: NIST ACVP vectors, 347 tests, real run"])
    set_paras(shape(s3, "Text 17"), ["Signed observation; tamper 401, replay 409"])
    frame = shape(s3, "Shape 20")
    txt = shape(s3, "Text 21")
    txt._element.getparent().remove(txt._element)
    s3.shapes.add_picture(str(ROOT / "ppt/diagrams/18_submission_architecture.png"), frame.left, frame.top, frame.width, frame.height)

    # ---- slide 4: feasibility
    s4 = s[3]
    set_paras(shape(s4, "Text 1"), [TEAM])
    set_paras(shape(s4, "Text 7"), ["Phases 0-3 built and tested (347/347)", "Runs on a laptop + USB webcam", "Gap: trust and recovery code"])
    set_paras(shape(s4, "Text 10"), ["ESP32 board unconfirmed; firmware unvalidated", "ESP32-side PQC unproven (research item)", "AGPL-3.0 model; PQC library not audited"])
    set_paras(shape(s4, "Text 13"), ["Software device agent keeps work unblocked", "Swappable detector and crypto interfaces", "Specify trust model before code; dashboard cut first"])
    set_paras(shape(s4, "Text 18"), ["Build & explore - Phases 0-3 done"])
    set_paras(shape(s4, "Text 22"), ["Demo evaluation - signed observation, tamper 401, replay 409"])
    set_paras(shape(s4, "Text 26"), ["Final jury pitch - evidence, limits, trust-engine roadmap"])

    # ---- slide 5: impact (measured numbers only; no deployment estimates exist)
    s5 = s[4]
    set_paras(shape(s5, "Text 1"), [TEAM])
    for big, cap, n_big, n_cap in (("347", "automated tests pass (347/347)", "Text 6", "Text 7"),
                                   ("70", "NIST test vectors agree (ML-KEM, ML-DSA)", "Text 9", "Text 10"),
                                   ("11", "signatures re-verified; altered copies rejected", "Text 12", "Text 13")):
        set_paras(shape(s5, n_big), [big])
        set_paras(shape(s5, n_cap), [cap])
    set_paras(shape(s5, "Text 16"), ["Operators of camera + sensor AIoT deployments", "Long-lived devices facing future quantum threats"])
    set_paras(shape(s5, "Text 18"), ["Security: forged, modified, replayed observations rejected (tested)", "Operational: explainable trust decisions (planned)",
                                     "Economic: no specialised hardware (laptop, USB webcam, ESP32)", "Social / environmental: not assessed yet"])
    set_paras(shape(s5, "Text 19"), ["All numbers measured in this prototype; no deployment impact is estimated."])

    # ---- slide 6: references and ethics
    s6 = s[5]
    set_paras(shape(s6, "Text 1"), [TEAM])
    set_paras(shape(s6, "Text 7"), ["NIST FIPS 203 (ML-KEM): csrc.nist.gov/pubs/fips/203/final", "NIST FIPS 204 (ML-DSA): csrc.nist.gov/pubs/fips/204/final",
                                    "NIST ACVP test vectors: github.com/usnistgov/ACVP-Server", "pqcrypto 1.0.0 (Apache-2.0): pypi.org/project/pqcrypto",
                                    "YOLO11n / Ultralytics (AGPL-3.0): github.com/ultralytics/ultralytics"])
    set_paras(shape(s6, "Text 9"), ["Video frames are never stored or transmitted", "Attack demos run only against our own local gateway",
                                    "AI false positives / negatives possible; not yet measured"])

    # ---- remove the "how to use this template" slide (its own note: delete before submitting)
    delete_slide(prs, 6)
    out = Path(a.out)
    prs.save(str(out))
    print(f"template sha256 {digest}")
    print(f"wrote {out.name}: {len(prs.slides)} slides (template limit: 6 including title)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
