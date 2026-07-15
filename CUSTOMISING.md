# Customising the research supervision workspace

Version 1.2.0 supports two preparation routes while retaining one stable rendering boundary:

- **Structured Mode** renders an approved eight-field JSON file directly.
- **Folder Mode** inventories a folder or ZIP, supports source-grounded drafting and stops for researcher approval before converting approved items to the same eight-field schema.

Customisation may change presentation and workflow defaults. It must not invent research content, transfer material between categories, weaken provenance checks or bypass the approval gate silently.

## Use Structured Mode

The input must contain exactly `project_title`, `recent_progress`, `completed_work`, `key_findings`, `unresolved_questions`, `decisions_required`, `next_actions` and `timeline`.

From the Skill directory, build with the default presentation:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html
```

Build with an optional presentation configuration:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html --config CONFIG.json
```

Open the result locally and compare every displayed item with its approved source field.

## Use Folder Mode

Ask the coding agent to use the Skill rather than treating `folder_mode.py` as a summarisation program. The helper inventories and validates; the agent must read the source material with suitable file-reading tools and prepare the provenance-bearing draft.

A recommended request is:

> Use $research-briefing-dashboard to review all materials in ./Supervisor_Meeting_Materials. The reporting period is 1 June to 14 July 2026. Prepare a source-grounded draft for my supervisor meeting, show me any conflicts or unclear items, and generate the final HTML only after I approve the draft.

Choose a new private review directory outside both the source folder and the public repository. From the Skill directory, inventory a folder or ZIP:

```bash
python3 scripts/folder_mode.py inventory SOURCE REVIEW_DIR \
  --reporting-period "1 June to 14 July 2026" \
  --meeting-purpose "Prepare the next supervisor meeting" \
  --attention-topic "Methods wording"
```

Repeat `--attention-topic` or `--exclude` when required. The command creates exactly:

- `source_inventory.csv`;
- `source_map.md`;
- `briefing_draft.json`;
- `unresolved_items.md`; and
- `excluded_files.md`.

If inventory used an exclusion, repeat the exact option when validating and finalising. For example:

```bash
python3 scripts/folder_mode.py inventory SOURCE REVIEW_DIR \
  --exclude "private_working_notes"
python3 scripts/folder_mode.py validate-review SOURCE REVIEW_DIR \
  --exclude "private_working_notes"
python3 scripts/folder_mode.py finalise SOURCE REVIEW_DIR FINAL_DIR \
  --approval APPROVAL.json \
  --exclude "private_working_notes"
```

The validator recomputes exclusions from these command-line options. Editing `source_inventory.csv` to label a file as explicitly excluded is not sufficient and is rejected.

Excluded directories are still inventoried recursively using metadata only. Their descendant paths are recorded without reading or hashing file content, which lets the final validator prevent an excluded filename from appearing in the shareable briefing.

The agent must then review every included source, update `read_status`, populate the draft and source map, and record conflicts or limitations. Files requiring readers that are unavailable remain visible as unsupported or unreadable. Never claim that a file type was reviewed merely because the inventory recognised its suffix.

### Complete the approval gate

Before final generation, the agent presents every proposed item with provenance, confidence, wording basis and uncertainty. The researcher can approve, edit, remove, reclassify or add items. Proposed inferred content must remain clearly marked.

After the researcher responds, the agent updates each item and issue, then validates the review set:

```bash
python3 scripts/folder_mode.py validate-review SOURCE REVIEW_DIR
```

The command returns a SHA-256 digest bound to the five review artefacts and the current source hashes. Create the approval file privately; do not place it in the source folder, public repository or downloadable Skill:

```json
{
  "schema_version": 1,
  "review_digest": "lowercase-sha256",
  "approve_finalisation": true,
  "approved_inferred_item_ids": [],
  "acknowledged_issue_ids": []
}
```

The two arrays must exactly match the inferred items and accepted issues in the final draft. A changed source or review artefact invalidates this approval.

Generate the four final files only after approval:

```bash
python3 scripts/folder_mode.py finalise SOURCE REVIEW_DIR FINAL_DIR \
  --approval APPROVAL.json
```

The output directory contains exactly:

- `final_briefing.html`;
- `final_briefing_input.json`;
- `final_source_map.md`; and
- `final_validation_report.md`.

If the researcher explicitly asks for generation without review, `--allow-unconfirmed` can replace `--approval`. This exceptional route displays an unconfirmed-draft warning, rejects inferred items, presents all retained issues as open for review and records the bypass. Do not make it a local default.

## Customise presentation settings

From the repository root, copy the partial example configuration and edit the copy:

```bash
cp research-briefing-dashboard/examples/briefing_config.json my-briefing-config.json
```

The builder merges a partial configuration with `research-briefing-dashboard/config/default_config.json`. Only the following keys are supported:

- `briefing_label`: non-empty text displayed above the project title.
- `group_order`: an exact permutation of `overview`, `progress_evidence`, `discussion` and `actions_timeline`.
- `group_labels`: replacement labels for one or more of those four group identifiers.
- `theme.accent` and `theme.highlight`: six-digit hexadecimal colours such as `#174f73`.
- `features.search`, `features.counts`, `features.collapse_controls`, `features.meeting_state` and `features.print`: `true` or `false`.

Unknown keys and invalid values are rejected. Group labels and ordering are presentation choices only; the fields within each group remain fixed. The Folder Mode Evidence Explorer is generated from approved provenance and remains separate from the four configurable briefing groups.

## Customise the Evidence Explorer

Folder Mode passes a validated evidence sidecar to the stable builder. Each record is bound to an exact final item by identifier and SHA-256 text digest. Routine theme configuration applies to the whole workspace, including the explorer.

For deeper changes, edit `research-briefing-dashboard/assets/briefing_template.html` and the corresponding rendering logic in `research-briefing-dashboard/scripts/build_briefing.py` together. Preserve:

- strict validation of evidence identifiers, hashes and enumerations;
- relative source paths only;
- no source excerpts, absolute local paths, or excluded and uncited filename disclosure;
- separate presentation of open review boundaries, accepted boundaries and resolved issues;
- content escaping and no external network dependency;
- a usable no-JavaScript reading order;
- keyboard navigation, visible focus and mobile layout;
- print expansion of every briefing and evidence section; and
- backward compatibility for Structured Mode without an evidence sidecar.

Do not edit generated HTML to correct research content. Correct the source-grounded review or the structured input and rebuild.

## Test changes

Run the standard-library tests from the repository root:

```bash
python3 -m unittest discover \
  -s research-briefing-dashboard/tests \
  -p 'test_*.py' \
  -v
python3 -m unittest discover \
  -s tests \
  -p 'test_*.py' \
  -v
```

Run the real browser interaction suite with Playwright and Chromium available:

```bash
python3 -m unittest \
  research-briefing-dashboard/tests/test_browser_interactions.py \
  -v
```

A skipped browser test is not sufficient for a release. Verify both Structured and Folder examples through `file://` and a local static server, then inspect wide and approximately 390-pixel views, keyboard operation, search, filters, collapse controls, Evidence Explorer links, meeting-state import and export, print output, console messages and network requests.

Rebuild a configured Structured Mode example and compare it with the tracked output:

```bash
tmp_dir="$(mktemp -d)"
python3 research-briefing-dashboard/scripts/build_briefing.py \
  research-briefing-dashboard/examples/meeting_brief.json \
  "$tmp_dir/configured.html" \
  --config research-briefing-dashboard/examples/briefing_config.json
cmp "$tmp_dir/configured.html" \
  research-briefing-dashboard/examples/meeting_brief.html
```

Run publication validation after any documentation, example, packaging or website change:

```bash
python3 scripts/validate_publication.py
```

## Rebuild the downloadable ZIP

Rebuild the archive only after tests and publication validation pass:

```bash
python3 scripts/package_skill.py
python3 -m zipfile -t Supervisor_Meeting_HTML_Skill.zip
python3 scripts/validate_publication.py
```

The packager creates the archive atomically with stable member timestamps. Inspect the archive inventory before publication. It must contain only the allow-listed Skill source, configuration, tests, licences and sanitised examples. It must not contain real source material, ad hoc review directories, approval files, final briefings, meeting-state exports, browser artefacts, caches, private paths or quality-assurance notes.

## Accessibility and confidentiality

- Keep body text at least 16 pixels and interactive targets at least 44 by 44 pixels.
- Check colour contrast, visible keyboard focus, heading order, labels, narrow-screen layout and print output after changing the template or theme.
- Do not remove the skip link, semantic controls, no-JavaScript fallback or reduced-motion support.
- Treat source folders, review artefacts, approval JSON, generated HTML and meeting-state exports as potentially confidential.
- Do not promise that agent-processed source text remains only on the device; it may enter the coding agent's model context.
- Keep working and final directories private until a researcher has checked their content, paths and evidence boundaries.
- Approval to generate a briefing is not approval to publish or share it.
