---
name: research-briefing-dashboard
description: Use when approved research meeting notes need a confidential, self-contained offline supervisor meeting workspace with searchable content and exportable meeting state.
---

# Research briefing dashboard

Build one offline HTML supervisor meeting workspace from approved, sanitised notes. Treat the eight input fields as the complete factual boundary.

## Prepare the input

Create UTF-8 JSON with exactly these keys:

```json
{
  "project_title": "…",
  "recent_progress": ["…"],
  "completed_work": ["…"],
  "key_findings": ["…"],
  "unresolved_questions": ["…"],
  "decisions_required": ["…"],
  "next_actions": ["…"],
  "timeline": ["…"]
}
```

Supply non-empty text for `project_title`. Supply an array of non-empty text for every other key; use an empty array when nothing was approved. Do not add keys.

Preserve wording and field placement. Never infer, combine, relabel or transfer content. In particular, do not turn an unresolved question into a finding or decision, and do not add dates, owners, risks, mitigations or actions that are absent from the supplied fields. Configuration may change presentation only; it must not alter this factual boundary.

## Build the workspace

Run the legacy command from the Skill directory to use the default presentation:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html
```

To apply an optional presentation override, copy and edit `examples/briefing_config.json`, then run:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html --config CONFIG.json
```

The optional configuration can change the briefing label, group order, group labels, theme colours and enabled interface features. It cannot change, add or relocate meeting content.

## Check the output

Open `OUTPUT.html` offline in a browser. Compare every displayed item with the corresponding JSON value, field by field. Confirm that the four workspace groups are present, every approved item remains in its source field, empty arrays display exactly `No items supplied.`, and no new factual content has appeared. Test the enabled search, navigation, collapse and print controls. Correct the input or configuration and rebuild if a check fails; do not patch the generated HTML.

## Use meeting state safely

When meeting state is enabled, the workspace can record discussion status, decision status, action completion and notes. Use **Export state** to save those annotations as JSON and **Import state** to restore them to the same briefing. The exported meeting-state file is separate from the eight-field source JSON and does not modify or become source content.

Exported state may contain confidential notes. Keep it in an approved local location, inspect it before sharing, and do not upload it to an external service. Import only a state file produced for the same briefing.

Return the generated HTML as the exact requested deliverable. Do not append an executive summary, recommendations, meeting record or speculative material.

## Confidentiality

Treat source notes, generated HTML and exported meeting state as confidential. Use sanitised identifiers, keep the files in approved local locations and review all content before sharing.

## Common mistakes

- Omitting a required key instead of supplying an empty array.
- Adding participant, author, risk or meeting-date keys.
- Reframing questions as proposed decisions to make the briefing seem actionable.
- Using configuration to rename a group in a way that changes the meaning of its source fields.
- Editing the template or builder for one meeting rather than correcting the input JSON.
- Treating exported meeting state as a replacement for the approved source JSON.
- Sharing the file before completing the field-by-field comparison.
