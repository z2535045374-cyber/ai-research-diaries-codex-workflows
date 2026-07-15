# Folder Mode design

Version 1.2.0 adds a source-grounded preparation layer around the existing deterministic HTML builder. It does not replace the eight-field rendering contract.

## User journeys

### Structured Mode

The researcher supplies the existing eight-field JSON document and runs:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html
```

This remains the shortest route when the content has already been approved.

### Folder Mode

The researcher supplies a folder or ZIP archive, a reporting period where known, the purpose of the meeting and any attention topics. The coding agent then:

1. inventories the source without following symbolic links or silently omitting files;
2. reads supported material with the tools available in its environment;
3. distinguishes likely current, superseded, duplicated, excluded and unreadable files;
4. prepares a provenance-bearing draft and records conflicts or uncertainty;
5. stops for the researcher to approve, edit, remove, reclassify or add items;
6. converts only the reviewed draft to the stable eight-field input;
7. invokes `build_briefing.py`, attaches the approved evidence map as an optional Evidence Explorer, opens the HTML and verifies the result.

The normal Folder Mode prompt is:

> Use $research-briefing-dashboard to review all materials in ./Supervisor_Meeting_Materials. The reporting period is 1 June to 14 July 2026. Prepare a source-grounded draft for my supervisor meeting, show me any conflicts or unclear items, and generate the final HTML only after I approve the draft.

## Separation of responsibilities

The coding agent performs semantic reading and conservative classification because those tasks depend on the supplied sources and the environment's document readers. Deterministic scripts enforce the parts that must not depend on model judgement:

- `folder_mode.py inventory` inventories a folder or safely inspects a ZIP, applies exclusions, hashes files, detects exact duplicates and filename-based version groups, and creates the five required pre-review artefacts;
- `folder_mode.py validate-review` validates the provenance-bearing draft, recomputes any command-line exclusions and binds the five review artefacts to the current source fingerprints;
- `folder_mode.py finalise` repeats the exclusion check, enforces the approval gate, converts approved items to the existing eight-field schema, prepares a temporary approved evidence manifest, invokes the existing builder and creates the four required final artefacts;
- `build_briefing.py` remains the final rendering layer for both modes. Its two existing commands remain unchanged; Folder Mode may use a new optional evidence-manifest argument.

The scripts never invent or semantically classify research content.

## Evidence Explorer

Folder Mode can add a fifth, optional Evidence Explorer group to the generated workspace. It uses a compact evidence-index pattern to connect approved briefing items with their source metadata without embedding discipline-specific research content or unrelated study tools.

The Evidence Explorer contains only approved metadata derived from the final source map:

- item-level links from each briefing statement to its supporting sources;
- search and filters for briefing category, confidence and wording basis;
- summary counts for final items, source files, directly stated items, conservative summaries and explicitly approved inferences;
- evidence cards showing the briefing item, relative source name, granular location, relevant date where known, confidence and wording basis;
- a compact source register showing which approved briefing items use each source;
- open review boundaries, accepted evidence boundaries and resolved issues as distinct outcomes.

No source excerpt, absolute path, excluded or uncited filename, document author metadata or hidden source content is embedded by default. Unconfirmed generation neutralises accepted or resolved labels and presents retained issues as open for review. The explorer is an audit aid, not proof that a statement is academically correct. It remains fully visible when JavaScript is unavailable, expands in print and uses the same offline, keyboard-accessible design system as the meeting workspace.

The optional builder interface is additive:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html --evidence EVIDENCE.json
```

The evidence manifest is validated against the eight-field payload. Every evidence item must reference a real one-based briefing item identifier and carry the SHA-256 of the exact final text. An unknown item, mismatched text hash, unknown source, absolute path or invalid enumeration rejects the build without changing an existing output. Structured Mode without `--evidence` retains the Version 1.1 eight-field input contract and command forms; release validation checks its generated output against the tracked Structured Mode example.

## Pre-review artefacts

Folder Mode creates these files in its working directory:

- `source_inventory.csv`: one row for every discovered source, excluded item and unreadable or unsupported file;
- `source_map.md`: a human-readable map linking each proposed item to its source locations;
- `briefing_draft.json`: the reviewable draft and its provenance;
- `unresolved_items.md`: conflicts, uncertainties, ambiguous versions and reading limitations;
- `excluded_files.md`: every default or user exclusion and its reason.

`source_inventory.csv` records a stable source identifier, relative path, detected type, size, modified date when available, SHA-256 digest when read, inclusion status, reader requirement, duplicate group, version group, version role, ambiguity and confidentiality flags, and reason. Modified dates support version analysis but are never treated as authority on their own.

## Draft contract

`briefing_draft.json` uses schema version 1. The title and each proposed list item carry:

- `text`;
- `confidence`: `high`, `medium` or `low`;
- `wording_basis`: `directly_stated`, `conservatively_summarised` or `inferred`;
- `review_status`: `pending`, `approved` or `removed`;
- `inference_approved`: a boolean that must be true before an inferred item can be finalised;
- one or more provenance records with `source_id`, `source_file`, `location` and `relevant_date` where available.

The document also records the supplied context and open issues. Issue types include competing versions, numerical conflict, interpretation uncertainty, unclear date or owner, possible confidentiality risk, missing reporting period and unreadable source. Each issue remains `open` until the researcher resolves or explicitly accepts it.

The finaliser rejects:

- unknown or missing schema keys;
- invalid types or enumerations;
- missing provenance for a proposed item;
- any pending item;
- an approved inferred item without explicit inference approval;
- any open issue;
- text that is not valid for the existing eight-field builder.

Removed items remain in the internal draft for auditability but never enter the final input or HTML.

## Review gate

Before final generation, the agent displays the proposed title and all seven categories with source references, confidence, wording basis, conflicts and uncertainties. It asks the researcher to approve, edit, remove, reclassify or add items. The agent records the result in the draft only after the researcher responds.

After the reviewed draft is settled, the agent computes a SHA-256 review digest over all five review artefacts and the current source hashes. The user approval record binds approval to that digest, explicitly allow-lists every inferred item and acknowledges any accepted unresolved, excluded or confidentiality issue. Any change to a source or review artefact invalidates the approval.

If the researcher explicitly requests generation without review, the finaliser requires an explicit `--allow-unconfirmed` flag. The generated workspace uses a visible `Unconfirmed draft` briefing label, retains issues only as open for review and records the bypass in the validation report. This path is never the default.

## Final artefacts

After approval, Folder Mode creates:

- `final_briefing.html`;
- `final_briefing_input.json` using exactly the existing eight keys;
- `final_source_map.md` containing only final approved items, shareable issue outcomes and their provenance;
- `final_validation_report.md` recording the review status, item reconciliation, builder result, offline checks and remaining browser checks.

Generation rehashes the sources to guard against changes after review and is staged in a temporary directory. Validation failures do not leave a partially generated final set.

## Source handling

The inventory recognises:

- directly readable text: Markdown, text, CSV, JSON, HTML, LaTeX, BibTeX, YAML, TOML, SQL and common analysis or source-code files;
- document readers required: DOCX, PDF, XLSX and PPTX;
- ZIP as an input container.

Recognition does not claim successful extraction. The agent records whether each included file was actually read. If a required document reader is unavailable or a file is damaged, the file remains in the inventory and is listed in `unresolved_items.md`.

Default exclusions cover hidden system files, Office temporary files, dependency and cache directories, build or distribution directories, earlier generated briefing outputs and explicit user exclusions. Directory exclusions apply recursively. Descendants are inventoried using metadata only, without content reads or hashes, so excluded filenames remain available to the final disclosure guard. An explicit `--exclude` must be repeated for inventory, review validation and finalisation, so an editable inventory reason cannot create an exclusion retrospectively. The generic `outputs` directory is not excluded because it can contain primary research work. Symbolic links are listed but not followed.

ZIP processing uses bounded streaming and rejects absolute paths, parent traversal, backslash traversal, symbolic links, encrypted or duplicate members, case-fold or Unicode-normalisation collisions, nested archives, excessive member counts, excessive expansion, suspicious compression ratios and individual oversized members. It does not execute or import code, macros, HTML, JavaScript or spreadsheet formulae.

## Version and duplicate rules

Exact duplicates are identified by SHA-256 digest. Possible versions are grouped by a conservative filename stem after removing explicit version markers such as `v1`, `v2`, `previous`, `current` and dated suffixes. A likely current version is assigned only when an explicit marker or version sequence supports it. Modified time is supporting evidence only.

Competing `final` or `current` files, equal highest version markers, materially different files with ambiguous names and conflicting content are surfaced for researcher clarification. Superseded files remain visible in the inventory and are not counted as separate progress without source-grounded justification.

## Confidentiality boundary

Folder Mode scripts do not make network requests. The coding agent may still process source text in its model context, so the Skill first asks the researcher to confirm that the selected material is approved for Codex processing. If not, it performs metadata-only inventory and asks for sanitised extracts. Filenames and lightweight text checks can flag possible confidential content, but they cannot prove that a source is safe to share. The draft, source map, working files and final HTML must be treated as confidential until reviewed.

Final HTML contains the approved briefing text and its approved relative source metadata. It does not embed absolute paths, source excerpts, source-map notes, excluded or uncited filenames, excluded files or hidden source content.

## Verification

Automated tests cover inventory completeness, recursive and command-bound exclusions, ZIP safety, duplicate and version signals, absolute-path rejection, atomic failures, draft validation, provenance, digest-bound review blocking, inferred-item approval, open, accepted and resolved issue semantics, final conversion, Evidence Explorer disclosure boundaries and legacy builder compatibility. A sanitised mixed-source example provides one current version, one previous version, one irrelevant file and at least one deliberately uncertain item.

Browser checks cover the final HTML's navigation, search, collapse controls, meeting state, print layout, offline behaviour and narrow-screen presentation. A separate agent forward test verifies that the Skill follows the review gate rather than generating prematurely.
