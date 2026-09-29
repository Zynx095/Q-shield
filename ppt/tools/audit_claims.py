"""Scan every presentation text source for strong-claim terms and list each hit for manual verification.

    python ppt/tools/audit_claims.py [--json ppt/evidence/claim-audit-hits.json]

Sources scanned: both .pptx files (slide text + speaker notes), figure text (string literals in the figure
generators), and the presentation markdown files. The scan does not decide anything: each hit is reviewed
against the implementation and the verdict is recorded in ppt/claim-audit.md.
"""
import ast
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pptx import Presentation

ROOT = Path(__file__).resolve().parents[2]
PPT = ROOT / "ppt"

TERMS = {
    "quantum safe": r"quantum[- ]safe", "quantum resistant": r"quantum[- ]resist", "quantum proof": r"quantum[- ]proof",
    "secure": r"\bsecur(e|ed|es|ity|ing)?\b", "AI": r"\bAI\b|\bAIoT\b", "self-healing": r"self[- ]heal",
    "real-time": r"real[- ]time", "novel": r"\bnovel", "prevent": r"\bprevent", "detect": r"\bdetect",
    "guarantee": r"\bguarant", "protected": r"\bprotect", "unhackable/100%": r"unhackab|100 ?%", "first": r"\bfirst\b",
    "trust score": r"trust score", "accuracy": r"\baccura",
}


def pptx_texts(path):
    prs = Presentation(str(path))
    for i, s in enumerate(prs.slides, 1):
        for sh in s.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                yield f"{path.name} slide {i}", sh.text_frame.text
        if s.has_notes_slide:
            yield f"{path.name} slide {i} NOTES", s.notes_slide.notes_text_frame.text


def figure_texts(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 8:
            yield f"{path.name}:{node.lineno}", node.value


def md_texts(path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            yield f"{path.relative_to(ROOT)}:{n}", line


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    sources = []
    for f in ("Q-SHIELD_full_deck.pptx", "Q-SHIELD_idea_submission.pptx"):
        sources += list(pptx_texts(PPT / f))
    for f in ("make_figures.py", "figures_more.py"):
        sources += list(figure_texts(PPT / "tools" / f))
    for f in ("slide-content.md", "speaker-notes.md", "judge-qa.md", "demo-script.md", "README.md"):
        if (PPT / f).exists():
            sources += list(md_texts(PPT / f))
    hits = []
    for where, text in sources:
        for term, rx in TERMS.items():
            for m in re.finditer(rx, text, flags=re.I):
                lo, hi = max(0, m.start() - 70), min(len(text), m.end() + 70)
                hits.append({"term": term, "where": where, "snippet": " ".join(text[lo:hi].split())})
    by_term = Counter(h["term"] for h in hits)
    print("hits per term:", dict(by_term))
    strong = [h for h in hits if h["term"] in ("quantum safe", "quantum resistant", "quantum proof", "real-time", "novel", "prevent", "guarantee",
                                               "unhackable/100%", "first", "trust score", "accuracy", "self-healing", "detect", "protected")]
    seen = defaultdict(set)
    for h in strong:
        key = (h["term"], h["snippet"])
        if key in seen[h["term"]]:
            continue
        seen[h["term"]].add(key)
        print(f"[{h['term']}] {h['where']}: ...{h['snippet']}...")
    if a.json:
        Path(a.json).write_text(json.dumps(hits, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
