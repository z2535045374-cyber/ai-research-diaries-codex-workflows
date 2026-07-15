# Folder Mode test results

## Release candidate

- **Target release:** Version 1.2.0
- **Test date:** 15 July 2026
- **Environment:** macOS, Python 3 and Chromium
- **Public test data:** sanitised synthetic research material only

## Test scope

Folder Mode was tested as a preparation layer around the existing deterministic eight-field builder. The checks covered recursive inventory, exclusions, source-reading records, duplicate and version signals, provenance, uncertainty, researcher approval, final conversion, the Evidence Explorer and publication packaging. Structured Mode remained in the regression suite.

## Baseline comparison

An unprimed control run without the Skill produced plausible meeting prose, but it did not create a complete source inventory, item-level provenance, the five review artefacts, a digest-bound approval record or a deterministic final build. This comparison supports the need for explicit Skill instructions and mechanical validation; it is not a claim about every possible agent response.

## Sanitised mixed-source example

The public example contains seven synthetic files:

- a dated progress note;
- a previous manuscript version;
- a current manuscript version;
- a small CSV results check;
- a supervisor-comment text file;
- a static analysis script; and
- an irrelevant lunch-menu file.

Results:

- **PASS** — all seven discovered files were recorded in `source_inventory.csv`.
- **PASS** — all six included sources were read statically; the script was not executed.
- **PASS** — the current and previous manuscript versions were distinguished without treating modification time as authority.
- **PASS** — the irrelevant file was excluded, recorded and not used as evidence.
- **PASS** — item-level provenance was retained in the draft and final Evidence Explorer.
- **PASS** — a deliberately uncertain classification remained visible for researcher review.
- **PASS** — one inferred next action required explicit item-level approval.
- **PASS** — the approved run generated the four required final files.
- **PASS** — the generated workspace exposed ten evidence records and ten item-to-evidence links.
- **PASS** — Evidence Explorer filtering, reset, source links and a 390-pixel layout worked in Chromium with no console errors.
- **PASS** — accepted boundaries and resolved issues used distinct labels, counts and source-map headings; unconfirmed output retained only neutral open-for-review language.

## Independent forward-use test

A separate agent received only the published Skill instructions and the sanitised source folder. It created exactly the five required review artefacts in a temporary directory and stopped before approval.

Results:

- **PASS** — all seven sources were accounted for and the six included sources were read.
- **PASS** — the explicit statement that Version 2 superseded Version 1 was preserved in the source map; the older version did not create duplicate progress claims.
- **PASS** — the irrelevant file was excluded and recorded.
- **PASS** — no exact duplicate, numerical conflict, confidentiality flag, unsupported file or unreadable file was invented.
- **PASS** — three genuine gaps were reported: classification of a comparison paragraph, an absent action owner and an absent deadline.
- **PASS** — the proposed next action remained marked `inferred`, `pending` and not approved.
- **PASS** — no HTML, approval JSON or review digest was created before the researcher response.

The test also confirmed an intentional atomic-output rule: the chosen review-directory path must not already exist. The Skill instructions say to choose a new review directory so that an existing review cannot be overwritten silently.

## Automated validation

| Check | Result |
|---|---|
| Skill unit and browser suite | **PASS — 65 tests, 0 skipped** |
| Publication and archive suite | **PASS — 14 tests** |
| Real Chromium interaction tests | **PASS** |
| Skill Creator metadata validator | **PASS** |
| Legacy eight-field Structured Mode | **PASS** |
| Invalid JSON, wrong types and unknown keys | **PASS — rejected without partial output** |
| Unsafe ZIP paths, duplicate members and bounded extraction | **PASS — rejected without partial output** |
| Changed sources or review files after approval | **PASS — approval invalidated** |
| Forged or omitted command-line exclusion | **PASS — review validation rejected the mismatch** |
| Generic POSIX, Windows, UNC, home-directory and filesystem-URI paths | **PASS — rejected without partial output** |
| Excluded or uncited filename in shareable evidence | **PASS — blocked or omitted from the final output** |
| Wrong brief item, source, text digest or evidence enumeration | **PASS — build rejected atomically** |
| Unapproved inferred item or open issue | **PASS — finalisation blocked** |
| Deterministic package build | **PASS — repeated ZIP files were byte-for-byte identical** |
| Package integrity | **PASS — 32 allow-listed members, CRC valid** |
| Public privacy scan | **PASS** |

## Evidence Explorer validation

The final workspace was checked for:

- item-to-source links from approved briefing statements;
- evidence search and category, source, confidence, wording-basis and boundary filters;
- source catalogue and distinct open, accepted and resolved issue outcomes;
- briefing, evidence and source counts;
- keyboard access and visible focus;
- graceful full-content display without JavaScript;
- expanded evidence in print;
- relative source locations only; and
- no source excerpts, absolute machine paths, excluded or uncited filenames, or excluded files.

All checks passed on the sanitised example.

## Supported and unsupported material

The inventory recognises common text, Markdown, CSV, JSON, HTML, LaTeX, BibTeX, YAML, TOML, SQL and source-code files for static reading. DOCX, PDF, XLSX and PPTX are supported only when suitable readers are available in the coding environment. Damaged files, image-only PDFs without approved OCR, unsupported tracked changes, hidden content and macros remain listed as unreadable, partially read or unresolved; they are never silently discarded.

## Remaining limitations

- Semantic classification is performed by the coding agent and still requires researcher judgement.
- Filename and content signals can suggest versions, but they cannot establish authority in every project.
- Available document readers vary by environment.
- The deterministic scripts do not summarise research material by themselves.
- Source text reviewed by a coding agent may enter that agent's model context; researchers must confirm that material is approved for processing.
- Successful generation, compilation or polished evidence presentation does not verify academic accuracy.

## Release decision

The local Version 1.2.0 release candidate passed its Folder Mode, Evidence Explorer, regression, packaging and privacy checks. The Git tag must be created only after the same commit is deployed and the live GitHub Pages site passes download, layout and interaction checks.
