# Customising the supervisor meeting workspace

The builder accepts the same eight approved content fields in every presentation. Customisation changes how that material is displayed; it must not change, infer or relocate the source content.

## Copy an optional configuration

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

Unknown keys and invalid values are rejected. Group labels and ordering are presentation choices only; the fields within each group remain fixed.

## Build with or without configuration

Use the default presentation:

```bash
python3 research-briefing-dashboard/scripts/build_briefing.py \
  research-briefing-dashboard/examples/meeting_brief.json \
  /tmp/meeting-brief-default.html
```

Use a presentation override:

```bash
python3 research-briefing-dashboard/scripts/build_briefing.py \
  research-briefing-dashboard/examples/meeting_brief.json \
  /tmp/meeting-brief-custom.html \
  --config my-briefing-config.json
```

Open each output locally and compare every displayed item with its source field before sharing it.

## Make deeper presentation changes

Use configuration for routine labels, ordering, colours and feature switches. For a reusable capability that configuration cannot express, edit `research-briefing-dashboard/assets/briefing_template.html` and the corresponding rendering logic in `research-briefing-dashboard/scripts/build_briefing.py` together. Preserve the required template tokens, strict input validation, offline operation, content escaping, keyboard access, print behaviour and meeting-state validation.

Do not edit a generated briefing to correct content. Correct its source JSON or configuration and rebuild it.

## Test changes

Run the standard-library test suite from the repository root:

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

Then rebuild both presentations and confirm that the configured output matches the tracked sanitised example:

```bash
tmp_dir="$(mktemp -d)"
python3 research-briefing-dashboard/scripts/build_briefing.py \
  research-briefing-dashboard/examples/meeting_brief.json \
  "$tmp_dir/default.html"
python3 research-briefing-dashboard/scripts/build_briefing.py \
  research-briefing-dashboard/examples/meeting_brief.json \
  "$tmp_dir/configured.html" \
  --config research-briefing-dashboard/examples/briefing_config.json
cmp "$tmp_dir/configured.html" research-briefing-dashboard/examples/meeting_brief.html
python3 scripts/validate_publication.py "$tmp_dir/default.html" "$tmp_dir/configured.html"
```

The browser interaction test runs when a suitable local Playwright and Chromium installation is available; otherwise the standard-library suite reports the browser check as skipped.

## Rebuild the downloadable ZIP

Rebuild the archive only after the tests and publication validation pass. Start from a clean checkout so caches and exported meeting-state files are absent, then run:

```bash
python3 scripts/package_skill.py
python3 -m zipfile -t Supervisor_Meeting_HTML_Skill.zip
python3 scripts/validate_publication.py
```

The packaging script creates the archive atomically, includes the standalone MIT and CC BY 4.0 notices, and gives every member a stable timestamp. Inspect the archive inventory before publishing it. It must contain the current Skill source, configuration, tests and sanitised examples, and must not contain confidential inputs, exported meeting state, browser artefacts, caches or private working notes.

## Accessibility and confidentiality

- Keep body text at least 16 pixels and interactive targets at least 44 by 44 pixels.
- Check colour contrast, visible keyboard focus, heading order, labels, narrow-screen layout and print output after changing the template or theme.
- Do not remove the skip link, semantic controls or reduced-motion support.
- Treat input JSON, generated HTML and exported meeting-state JSON as potentially confidential.
- Exported state contains meeting annotations, remains separate from source content and should be stored only in an approved location.
- Review all content and state before sharing any file.
