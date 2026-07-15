# AI Research Diaries: two practical Codex workflows

This repository supports an approximately five-minute asynchronous contribution about two researcher-controlled workflows: local LaTeX production and a reusable research supervision workspace. Codex can reduce repetitive document work, but the researcher remains responsible for academic accuracy, confidentiality and final checking.

## Open the contribution

- [View the live Version 1.2.0 page](https://z2535045374-cyber.github.io/ai-research-diaries-codex-workflows/)
- [Browse the public source repository](https://github.com/z2535045374-cyber/ai-research-diaries-codex-workflows)

The public page uses embedded or relative assets only. A generated supervision workspace is a self-contained HTML file that can be opened through `file://` without an internet connection.

## The two workflows

1. **Edit and compile LaTeX locally.** Where the working environment permits, Codex can help edit approved LaTeX source, compile it with TeX Live, inspect logs and correct technical formatting. Successful compilation does not verify wording, citations, numerical results, interpretation or journal requirements.
2. **Prepare a research supervision workspace.** The reusable Skill creates an editable, offline HTML briefing through either Structured Mode or Folder Mode. Folder Mode adds source-grounded preparation, a researcher approval checkpoint and an Evidence Explorer; the existing eight-field builder remains the deterministic rendering layer.

## Two briefing approaches

### Structured Mode

Use Structured Mode when the researcher already has an approved JSON file containing exactly:

- project title;
- recent progress;
- completed work;
- key findings;
- unresolved questions;
- decisions required;
- next actions; and
- timeline.

From the Skill directory, generate the workspace with:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html
```

An optional presentation configuration remains available:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html --config CONFIG.json
```

### Folder Mode

Use Folder Mode when recent research materials already exist in a folder or ZIP and the researcher does not want to prepare the eight fields manually. The coding agent:

1. inventories the supplied source recursively;
2. reads supported material with the file-reading tools available in its environment;
3. identifies duplicates, possible versions, exclusions, unreadable files and uncertainties;
4. prepares five provenance-bearing review artefacts;
5. shows a source-grounded briefing draft to the researcher and stops for review;
6. binds approval to the reviewed files and current source hashes; and
7. invokes the unchanged eight-field builder only after approval.

The deterministic Folder Mode helper does not perform semantic summarisation on its own. The coding agent must actually inspect the sources, populate the draft and preserve provenance before validation can pass.

A full request can be as simple as:

> Use $research-briefing-dashboard to review all materials in ./Supervisor_Meeting_Materials. The reporting period is 1 June to 14 July 2026. Prepare a source-grounded draft for my supervisor meeting, show me any conflicts or unclear items, and generate the final HTML only after I approve the draft.

Or use the shorter request:

> Use $research-briefing-dashboard in Folder Mode on this project folder and prepare my next supervisor-meeting briefing.

The Folder Mode inventory recognises common text, Markdown, CSV, JSON, HTML and source-code formats directly. DOCX, PDF, XLSX and PPTX require suitable document readers in the coding environment. Damaged, unreadable or unsupported files must remain visible in the inventory and unresolved-items report; they are never silently ignored.

When a researcher explicitly excludes a file or directory, the same `--exclude` option must be repeated during `inventory`, `validate-review` and `finalise`. Validation recomputes the source inventory from those command-line exclusions; it does not trust an editable CSV reason as proof that an exclusion was requested.

See [CUSTOMISING.md](CUSTOMISING.md) for the complete commands, approval record and safe working-directory pattern. The architectural and security boundary is documented in [FOLDER_MODE_DESIGN.md](FOLDER_MODE_DESIGN.md).

## Researcher review checkpoint

Before final generation, the agent must show every proposed item with its source file, granular location, confidence, wording basis and relevant uncertainty. The researcher can approve, edit, remove, reclassify or add material. Inferred content requires explicit item-level approval, and unresolved issues must be resolved or knowingly accepted.

Normal finalisation requires a private approval JSON containing the SHA-256 digest returned by `validate-review`. Editing a source or review artefact after that point invalidates the approval. Explicit unconfirmed generation is available only as an exceptional bypass and produces a visible warning; it is not a substitute for researcher review.

## Evidence Explorer

An approved Folder Mode workspace includes an optional fifth group, **Evidence Explorer**. It provides:

- links between briefing items and approved source records;
- relative source paths and granular locations;
- relevant dates, confidence and wording basis;
- search and filters for category, source and evidence status;
- a source catalogue, accepted evidence boundaries and resolved issues shown as distinct outcomes; and
- keyboard-accessible, offline and print-friendly views.

The explorer does not embed source excerpts, absolute local paths, excluded or uncited filenames, private files or unpublished material that is not already needed for the approved briefing. Unconfirmed output uses neutral, open-for-review issue language rather than claiming that a boundary was accepted or resolved. A polished Evidence Explorer is a traceability aid, not proof that an academic claim is correct.

## Downloads

- [Download the TeX Live and Codex guide](TeX_Live_Codex_Guide.pdf)
- [Download the research supervision workspace Skill](Supervisor_Meeting_HTML_Skill.zip)

Review each file before sharing it. Source folders, review artefacts, approval records, generated HTML and exported meeting-state JSON may contain confidential material.

## Source layout

- [`index.html`](index.html): the public Version 1.2.0 contribution.
- [`404.html`](404.html): the GitHub Pages not-found page.
- [`research-briefing-dashboard/SKILL.md`](research-briefing-dashboard/SKILL.md): the two-mode coding-agent workflow and factual boundary.
- [`research-briefing-dashboard/scripts/folder_mode.py`](research-briefing-dashboard/scripts/folder_mode.py): safe inventory, review validation, approval binding and finalisation.
- [`research-briefing-dashboard/scripts/build_briefing.py`](research-briefing-dashboard/scripts/build_briefing.py): the stable eight-field renderer and optional evidence-manifest validator.
- [`research-briefing-dashboard/assets/briefing_template.html`](research-briefing-dashboard/assets/briefing_template.html): the self-contained HTML template.
- [`research-briefing-dashboard/config/default_config.json`](research-briefing-dashboard/config/default_config.json): the default presentation settings.
- [`research-briefing-dashboard/examples/folder-mode/`](research-briefing-dashboard/examples/folder-mode/): sanitised mixed-source Folder Mode example.
- [`research-briefing-dashboard/examples/meeting_brief.html`](research-briefing-dashboard/examples/meeting_brief.html): sanitised Structured Mode example.
- [`research-briefing-dashboard/tests/`](research-briefing-dashboard/tests/): unit and browser interaction checks.
- [`tests/`](tests/): repository-level publication validation regressions.
- [`scripts/package_skill.py`](scripts/package_skill.py): deterministic, atomic Skill ZIP packaging.
- [`scripts/validate_publication.py`](scripts/validate_publication.py): link, offline-dependency, privacy, metadata and archive checks.
- [`.github/workflows/validate.yml`](.github/workflows/validate.yml): automated tests and publication validation.
- [`CHANGELOG.md`](CHANGELOG.md): release history.

## Open-source customisation

Common presentation choices are available through a strict JSON configuration. Researchers can also fork the MIT-licensed source to change layout or add discipline-specific presentation features, provided they preserve source escaping, accessibility, offline behaviour, provenance validation and the approval gate. Configuration cannot move research content between the eight categories or make an unread source acceptable evidence.

See [CUSTOMISING.md](CUSTOMISING.md) for supported configuration keys and deeper source changes. See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change. Contributions must use British English and sanitised fixtures only.

The Skill was created primarily for Codex. It may be adapted for coding agents that support reusable project instructions and equivalent local file-reading capabilities, but universal compatibility is not claimed.

## Licences and disclaimer

Software, templates, scripts and implementation structure are available under the [MIT licence](LICENSE). Website prose, human-readable documentation, sanitised example prose and `TeX_Live_Codex_Guide.pdf` are available under [CC BY 4.0](CONTENT-LICENSE.md). The downloaded Skill includes standalone copies of both licence notices so the reuse boundary remains clear after extraction.

This is a personal HDR workflow contribution by Poming Zhang. It is not an official guide of The University of Western Australia, UWA Business School or OpenAI, and it does not imply their endorsement or affiliation. Tool availability varies by environment.
