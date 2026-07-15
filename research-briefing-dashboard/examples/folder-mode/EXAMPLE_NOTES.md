# Folder Mode sanitised example

This example demonstrates the approval-gated Folder Mode without using private research material.

## What the example contains

- `sources/` contains small synthetic Markdown, text, CSV and Python files.
- `review/` contains the five post-review artefacts. Every included source is marked as read, and all proposed items preserve relative provenance.
- `final/` contains the four outputs produced after a digest-bound synthetic approval.

The inventory recognises `manuscript_section_v2_current.md` as the current candidate and `manuscript_section_v1_previous.md` as the previous version. The current document also states explicitly that it supersedes the previous document, so the earlier wording is not counted twice. `irrelevant_lunch_menu.txt` is recorded as an explicit exclusion.

The example keeps one accepted classification uncertainty: the sources do not establish whether a comparison paragraph is a substantive finding or discussion content. It therefore appears as a question and meeting decision, not as a finding. One inferred next action was included only after explicit synthetic approval.

## Rebuild sequence

From the Skill directory:

```bash
python3 scripts/folder_mode.py inventory examples/folder-mode/sources REVIEW_DIR \
  --reporting-period "1 June to 14 July 2026" \
  --meeting-purpose "Review progress and agree the next document-preparation steps" \
  --attention-topic "Methods wording" \
  --attention-topic "Finding-versus-interpretation classification" \
  --exclude "irrelevant_lunch_menu.txt"
```

After the coding agent has read the files, populated the draft and shown it to the researcher, validate the review:

```bash
python3 scripts/folder_mode.py validate-review examples/folder-mode/sources REVIEW_DIR
```

Create a private approval file containing the returned digest, the approved inferred item ID `next_actions-1`, and the acknowledged issue ID `issue-1`. Then finalise:

```bash
python3 scripts/folder_mode.py finalise examples/folder-mode/sources REVIEW_DIR FINAL_DIR \
  --approval PRIVATE_APPROVAL.json
```

The approval file is deliberately not included in this repository. Approval to generate a briefing is not approval to publish either the sources or the review artefacts.
