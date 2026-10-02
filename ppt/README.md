# Q-SHIELD presentation package

## FINAL deck for Quant-A-Maze 3.O (use this one)

**`final/Q-SHIELD_QuantAMaze3.0_Final.pptx`**, with **`.pdf`**: 24 slides on the official Quant-A-Maze 3.O
template (`Quant-A-Maze.pptx`). The template asks for the PDF to be uploaded.

- **Template.** Every slide is a clone of one of the template's own pages, so the NITTE, Quant-A-Maze and Q-BITS
  logos, the orange band, the halftone strip and the bottom band are the organisers' artwork. The six official
  section headings are kept word for word; each opens its section, and every other slide carries its section as a
  marker. The template's two reference slides are removed, as it instructs.
- **Content.** The slide-by-slide plan, the diagram plan and the rules are in `final/SLIDE_PLAN.md`. Every number is
  from the repository, and its source is in the slide's speaker notes. The current figures are listed in
  `references/verified-facts.md` section 0.
- **Team fields.** Team name, lead name and contact are left as `[ to fill ]`. They were not supplied, and they must
  not be invented. Fill them on slide 1 in PowerPoint, then export the PDF again.
- **Rebuild:**
  ```
  python ppt/tools/quantamaze_deck/build.py
  powershell -File ppt/tools/render_deck.ps1 -Pptx ppt/final/Q-SHIELD_QuantAMaze3.0_Final.pptx -OutDir ppt/preview/quantamaze -Pdf ppt/final/Q-SHIELD_QuantAMaze3.0_Final.pdf
  ```
  The render uses the installed Microsoft PowerPoint. The previews in `preview/quantamaze/` are PowerPoint's own
  renders.
- **Fonts.** Titles use Bahnschrift SemiBold, body text Segoe UI, and technical strings Consolas; all ship with
  Windows. Bahnschrift is a variable font, so PowerPoint draws it as vector outlines in the PDF, with the text still
  searchable. Any other PowerPoint machine needs the fonts installed for the .pptx to look the same.
- The earlier decks below (`final/Q-SHIELD_FINAL_PRESENTATION.pptx`, `final/Q-SHIELD_QuantAMaze3.0_Submission.pptx`,
  and the September 24 decks) are superseded. They describe earlier phases.

---

## Earlier material (superseded; kept for reference)

## Earlier idea-submission deck (superseded)

**`Q-SHIELD_Idea_Submission_FINAL.pptx`** (+ `.pdf`): an original 6-slide deck designed from scratch. It does **not** use the sample's theme, layout, colours, fonts or shapes; the sample was used only for the constraints (max 6 slides, points and diagrams only, required headings, required title-slide fields). The required headings are kept verbatim: `IDEA TITLE`, `TECHNICAL APPROACH`, `FEASIBILITY AND VIABILITY`, `IMPACT AND BENEFITS`, `RESEARCH AND REFERENCES`, plus their sub-headings.
- Every diagram is built from native, editable PowerPoint shapes and connectors (each slide has exactly one picture: a generated background texture). Fonts: Segoe UI + Consolas (installed with Windows/Office; substitute if the presenting machine lacks them).
- Status language on every slide: **IMPLEMENTED** (green dot), **DESIGNED** (violet diamond), **NEXT** (amber chevron), always with the text label.
- Rebuild with the team's real details: `python ppt/tools/final_deck/build_final_deck.py --team-name "..." --members "..." --school "..." --contact "..." --ps-number "..." --track "..." [--title "..."]`, then `powershell -File ppt/tools/render_deck.ps1 -Pptx ppt/Q-SHIELD_Idea_Submission_FINAL.pptx -OutDir ppt/preview/final -Pdf ppt/Q-SHIELD_Idea_Submission_FINAL.pdf`. The only bracketed placeholders left are the team fields (team name, members, school, contact, problem statement number, track), because they were not supplied.
- Source: `tools/final_deck/` (`build_final_deck.py`, `kit.py`, `backgrounds.py`). Previews: `preview/final/`.
- The earlier template-filled deck (`Q-SHIELD_idea_submission.pptx`) and the 27-slide talk are kept for reference and are superseded for submission by this file.

**Status:** both decks are built from the repository's verified state (Phases 0-3 implemented; 347/347 tests). Trust engine, quarantine, recovery, evidence chain, digital twin and dashboard are shown only as designed/planned. The submission deck still contains **bracketed placeholders for team details**, which only the team can supply.

## Two decks

| File | Purpose | Slides |
|---|---|---|
| `Q-SHIELD_idea_submission.pptx` / `.pdf` | **Official-template idea submission.** Built by filling a copy of the organiser's sample (`PPT SAMPLE.pptx`); preserves size, branding, headings and footer. | **6** (template maximum, title included) |
| `Q-SHIELD_full_deck.pptx` / `.pdf` | Full technical talk for the live pitch / Q&A, own dark design matching the template palette. Every slide has speaker notes. | 21 main + appendix divider + 5 backup |

Template identification, its rules and every compatibility decision: `references/official-template-analysis.md`. The requested 17-slide structure could not be used for the submission because the template limits it to six slides; its content is spread across the 21-slide talk.

## Contents
| Path | What |
|---|---|
| `slide-content.md`, `speaker-notes.md` | full-deck text and notes, **generated** from `tools/deck_content.py` |
| `judge-qa.md` | prepared honest answers (all questions from the brief plus more) |
| `demo-script.md` | reproducible live demo with fallbacks and "do not" list |
| `claim-audit.md` | strong-claim audit against the implementation, wording changes, residual risks |
| `references/verified-facts.md` | every number allowed on a slide, with its source; wording rules |
| `references/official-template-analysis.md` | template found, rules, structure, compatibility |
| `evidence/` | raw evidence files and how each was produced (see its README) |
| `diagrams/` | 14 diagrams (PNG + SVG): architecture, closed loop, signed-observation flow, security domains, PQC session flow, observation-authentication flow, implementation status, validation flow, trust-engine preview, ESP32 status, roadmap, compact submission architecture |
| `assets/` | 4 measured-data charts: PQC benchmark, vision throughput, NIST evidence, test summary |
| `preview/` | PNG renders of each slide (from PowerPoint), for review only; regenerable |
| `tools/` | `make_figures.py` (+ `figures_more.py`), `deck_content.py`, `build_full_deck.py`, `build_submission_deck.py`, `render_deck.ps1`, `audit_claims.py` |

## Exact steps to produce the final presentation file
1. **Confirm the template.** `PPT SAMPLE.pptx` was found in `..\shadowguard-main\` (another project's folder; its slide 1 held a different project). Confirm with the organisers/team that it is the one for this submission. If a different file applies, pass it with `--template`.
2. **Get the team details** (problem statement number, official title if it differs, track/theme, team name, up to 4 members, school, team-leader contact).
3. **Rebuild the submission deck with them** (from the repository root):
   ```
   python ppt/tools/build_submission_deck.py --team-name "..." --members "A, B, C, D" --school "..." --contact "..." --ps-number "..." --track "..." [--title "..."]
   ```
4. **Export the PDF** the template requires, and render previews to check layout on your machine:
   ```
   powershell -File ppt/tools/render_deck.ps1 -Pptx ppt/Q-SHIELD_idea_submission.pptx -OutDir ppt/preview/submission -Pdf ppt/Q-SHIELD_idea_submission.pdf
   ```
   (uses the installed Microsoft PowerPoint; or open the .pptx and File > Export > PDF.)
5. **Open both files in PowerPoint and read every slide once.** Confirm there are no `[BRACKETS]` left, the six section headings are intact, and text fits (Arial/Calibri).
6. **Decide on the novelty wording.** The decks say "proposed integration" and make no "first" claim, because no prior-art survey exists (`docs/research/prior-art.md` is empty).
7. Regenerate everything from the repo at any time: `python ppt/tools/make_figures.py && python ppt/tools/build_full_deck.py && python ppt/tools/build_submission_deck.py [options]`, then re-run `python ppt/tools/audit_claims.py` after any wording change.

## Real captures still needed (none exist; none were fabricated)
- Terminal capture of `python -m pytest` showing 347 passed.
- Terminal/browser capture of the live path: vision run, then `GET /api/v1/observations` showing `"auth": "ML-DSA-65:vision-1"`, then `scripts/demo_forgery.py` showing 401 and the replay result.
- **A person in the restricted zone with `anomaly: true`.** This path has only been tested with a fake detector; it must be rehearsed live before it is shown or claimed.
- A photo of the physical setup (laptop + USB webcam). ESP32 photos, serial-monitor output and any hardware telemetry only after the board is connected, identified and flashed.
- Dashboard, trust-engine, quarantine or recovery screenshots: **not possible; those components do not exist.**

## Rules (enforced by `claim-audit.md`)
1. Implemented, designed and planned are never blurred; planned items are dashed/amber and labelled.
2. The ESP32 authenticates with HMAC-SHA256, which is **not** post-quantum. Never say the ESP32 or the whole system is quantum-safe.
3. No fabricated screenshots, graphs, accuracy values or benchmarks. FPS is speed, not accuracy.
4. No "first", "quantum-proof", "unhackable", "100% secure". Novelty = proposed integration.
5. Disclose the AGPL-3.0 licence of the YOLO model.
6. Do not copy the sample template's other-team details (names, contact) into any deck.
