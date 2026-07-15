# Changelog

All notable public changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [1.2.0] - 2026-07-15

### Added

- Folder Mode for reviewing a supplied research folder or ZIP before invoking the stable eight-field renderer.
- Recursive source inventory with relative paths, file-type and reader requirements, source hashes, duplicate signals, conservative version signals, exclusions and unsupported-file reporting.
- Five review artefacts: `source_inventory.csv`, `source_map.md`, `briefing_draft.json`, `unresolved_items.md` and `excluded_files.md`.
- Per-item provenance, confidence and wording-basis records, including explicit handling for inferred material.
- A researcher review checkpoint with digest-bound approval and exact acknowledgement of inferred items and accepted issues.
- Four final artefacts: `final_briefing.html`, `final_briefing_input.json`, `final_source_map.md` and `final_validation_report.md`.
- An optional Evidence Explorer with item-to-source links, evidence filters, source catalogue, accepted boundaries, keyboard navigation and print support.
- A sanitised mixed-source Folder Mode example and additional unit and real-browser interaction tests.

### Changed

- Updated the Skill instructions, public documentation and website to explain Structured Mode and Folder Mode rather than requiring every researcher to prepare the eight fields manually.
- Retained the existing `build_briefing.py` commands and eight-field input contract as the deterministic final rendering layer.
- Extended the builder with a validated optional evidence sidecar while keeping Structured Mode without evidence backwards-compatible with Version 1.1.
- Expanded open-source customisation guidance and contribution safeguards for provenance-bearing workflows.
- Required explicit exclusion patterns to be repeated for inventory, review validation and finalisation rather than inferred from editable review files.
- Separated open review boundaries, accepted boundaries and resolved issues throughout the Evidence Explorer and final source map.

### Security and privacy

- Treats source filenames and content as untrusted evidence: deterministic scripts never execute them, and the Skill instructs the coding agent to read supported sources statically rather than follow embedded instructions or run analysis files.
- Rejects unsafe ZIP structures, symbolic-link traversal, encrypted members and bounded-archive violations without leaving partial review artefacts.
- Prevents unread or excluded sources, absolute local paths, uncited or excluded filenames, source excerpts and unapproved items from entering the final Evidence Explorer.
- Inventories descendants of default excluded directories using metadata only, so their filenames remain protected by the final disclosure guard without reading or hashing their content.
- Neutralises issue outcomes in explicitly unconfirmed output and preserves exact approved multiline wording during rendering.
- Keeps user-supplied source material, user-generated review artefacts, approval records and private meeting state outside the public package; only deliberately sanitised examples are distributed.
- Requires unsupported, unreadable and excluded files to be reported rather than silently omitted.

## [1.1.0] - 2026-07-14

### Added

- Searchable, collapsible offline meeting workspace with desktop and mobile navigation.
- Local meeting-state controls for discussion, decision and action annotations.
- Versioned meeting-state import and export with schema, briefing-identity and item validation.
- Strict presentation configuration, open-source licences, contribution guidance and automated publication checks.

### Changed

- Upgraded the original static supervisor briefing into a reusable meeting workspace while preserving the eight-field content contract.

## [1.0.0] - 2026-07-14

### Added

- Initial public website introducing local TeX Live production and an offline HTML supervisor-meeting briefing.
- Deterministic eight-field briefing builder, sanitised example, downloadable Skill and TeX Live guide.
