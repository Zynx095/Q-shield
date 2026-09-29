# Official template: identification and compatibility

## What was found
- **File:** `PPT SAMPLE.pptx`, located outside this repository at `..\shadowguard-main\PPT SAMPLE.pptx` (a sibling project folder). SHA-256 `0c27eada12802728aac43cf314d1e1b640d2a91adfd0ddb12b9aeca2cb4ae5e8`. It was opened read-only; the hash was re-checked after building and is unchanged. It is **not copied into this repository** (it carries organiser branding and, in its first slide, another team's details).
- **Event:** "The Digital Mission 2026 - Idea Submission", Mini Hackathon, 23 September 2026, NVIDIA AI Lab; Cybersecurity x AI; Presidency University / ISACA Bangalore Chapter.
- **Not verified:** that this sample is the template for Q-SHIELD's own submission. It sits in another project's folder and slide 1 is filled with a different project's title and team. **Please confirm** it is the one you must use. If the organisers issued a different or newer file, rebuild with `--template <path>` (the builder asserts the same 7-slide structure).

## Template rules (from the template's own "How to use" slide)
1. Six slides maximum, title slide included; delete the "How to use" slide before submitting.
2. Points, diagrams and infographics only; no paragraphs.
3. Keep explanations precise and readable from the back of the room.
4. The idea must be the team's own and genuinely novel.
5. Use the template as given: do not remove or rename section headings.
6. Submission is compulsory; the PPT decides the shortlist.
7. Teams of 3-4 with at least one girl member; AI usage encouraged.
Also on slide 6: every link opens and is public; nothing copied without credit; team name on every slide; export as PDF as well as PPT.

## Structure (16:9, 13.333 x 7.5 in, dark theme `#070C18`, cyan `#35D6F0` and gold `#F2C14E` accents, Arial headings, Calibri body)
| # | Section | Fields |
|---|---|---|
| 1 | Title | problem statement number, title, track/theme, team name, members (max 4), school, team-leader contact |
| 2 | IDEA TITLE | idea line; 01 PROPOSED SOLUTION; 02 HOW IT SOLVES THE PROBLEM; 03 WHY IT'S DIFFERENT; optional visual strip |
| 3 | TECHNICAL APPROACH | 01 TECH STACK; 02 METHODOLOGY; 03 WHAT YOU DEMO; ARCHITECTURE / FLOW DIAGRAM frame |
| 4 | FEASIBILITY AND VIABILITY | FEASIBILITY; CHALLENGES & RISKS; MITIGATION; ONE-DAY EXECUTION PLAN (3 phases) |
| 5 | IMPACT AND BENEFITS | three metric cards; WHO IT HELPS; BENEFITS |
| 6 | RESEARCH AND REFERENCES | SOURCES BEHIND THE IDEA; ETHICS & DATA HANDLING; BEFORE YOU SUBMIT |
| 7 | HOW TO USE THIS TEMPLATE | delete before submitting |

## Compatibility decisions
- **Slide count:** the requested 17-slide structure cannot be used for the submission (limit is 6). The submission deck has **6 slides**; the longer story is a separate full technical deck (`Q-SHIELD_full_deck.pptx`, 21 main + 5 backup) for a live pitch or Q&A.
- **Preserved:** slide size, background, logos (Presidency University, ISACA), header pill, footer and page numbers, every section heading, layout, fonts and colours. Section headings are unchanged.
- **Filled:** field bodies only. A picture replaces the placeholder text in the diagram frame on slide 3. Slide 7 removed as instructed.
- **Impact cards (slide 5):** the template says to replace placeholder numbers with real estimates and say where they came from. There are no deployment-impact estimates for Q-SHIELD, so the cards show **measured prototype evidence** (347 tests, 70 NIST cases, 11 signatures) and the slide says no deployment impact is estimated. Do not invent user or cost numbers.
- **Novelty rule:** the template asks for a "genuinely novel" idea. Our wording is "proposed integration, not a new algorithm"; a prior-art survey has not been done (`docs/research/prior-art.md` is empty). Decide whether to strengthen this claim only after that survey.
- **Fields left as placeholders (must be supplied by the team, never copied from the sample):** `[NO.]` problem statement number, `[TRACK / THEME]`, `[TEAM NAME]` (slides 1-6), `[TEAM MEMBERS]`, `[SCHOOL]`, `[CONTACT]`. The title field carries "Q-SHIELD: QUANTUM-RESILIENT AIoT SECURITY"; replace it if the organisers require an official problem-statement title.
- **PDF:** `Q-SHIELD_idea_submission.pdf` is exported with the locally installed Microsoft PowerPoint (COM), as the template requires. Re-export after filling in the placeholders.
