# AI Research Diaries: two practical Codex workflows

This repository supports an approximately five-minute asynchronous contribution about two researcher-controlled workflows: local LaTeX production and reusable supervisor meeting workspaces. Codex can reduce repetitive document work, but the researcher remains responsible for academic accuracy, confidentiality and final checking.

## Open the contribution

- [View the live Version 1.1 page](https://z2535045374-cyber.github.io/ai-research-diaries-codex-workflows/)
- [Browse the public source repository](https://github.com/z2535045374-cyber/ai-research-diaries-codex-workflows)

The page and meeting example use embedded or relative assets only. The generated meeting workspace is a self-contained HTML file that works offline.

## The two workflows

1. **Edit and compile LaTeX locally.** Codex can help edit approved LaTeX source, compile it with an available TeX Live installation, inspect logs and correct technical formatting. Successful compilation does not verify wording, citations, results, interpretation or journal requirements.
2. **Prepare a supervisor meeting workspace.** The reusable Skill turns eight approved input fields into a searchable, collapsible offline briefing organised as Overview, Progress and evidence, Discussion workspace, and Actions and timeline. Optional meeting-state controls can export and import annotations without changing the supplied source content.

## Downloads

- [Download the TeX Live and Codex guide](TeX_Live_Codex_Guide.pdf)
- [Download the supervisor-meeting HTML Skill](Supervisor_Meeting_HTML_Skill.zip)

Review each file before sharing it. Generated HTML and exported meeting-state JSON may contain confidential material.

## Source layout

- [`index.html`](index.html): the public Version 1.1 contribution.
- [`404.html`](404.html): the GitHub Pages not-found page.
- [`research-briefing-dashboard/SKILL.md`](research-briefing-dashboard/SKILL.md): the coding-agent workflow and factual boundary.
- [`research-briefing-dashboard/scripts/build_briefing.py`](research-briefing-dashboard/scripts/build_briefing.py): the standard-library builder.
- [`research-briefing-dashboard/assets/briefing_template.html`](research-briefing-dashboard/assets/briefing_template.html): the self-contained HTML template.
- [`research-briefing-dashboard/config/default_config.json`](research-briefing-dashboard/config/default_config.json): the default presentation settings.
- [`research-briefing-dashboard/examples/meeting_brief.html`](research-briefing-dashboard/examples/meeting_brief.html): the sanitised interactive example.
- [`research-briefing-dashboard/tests/`](research-briefing-dashboard/tests/): unit and browser interaction checks.
- [`tests/`](tests/): repository-level publication validation regressions.
- [`scripts/package_skill.py`](scripts/package_skill.py): deterministic, atomic Skill ZIP packaging.
- [`scripts/validate_publication.py`](scripts/validate_publication.py): link, offline-dependency, privacy, metadata and archive checks.
- [`.github/workflows/validate.yml`](.github/workflows/validate.yml): standard-library tests and publication validation for pushes and pull requests.

## Skill quick start

Place `research-briefing-dashboard` in the Skills or project-instructions location supported by Codex or another compatible coding agent. Ask the agent to use `$research-briefing-dashboard`, or build directly from the Skill directory:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html
```

To apply an optional presentation configuration:

```bash
python3 scripts/build_briefing.py INPUT.json OUTPUT.html --config CONFIG.json
```

The input JSON must contain exactly `project_title`, `recent_progress`, `completed_work`, `key_findings`, `unresolved_questions`, `decisions_required`, `next_actions` and `timeline`. The Skill forbids inference or transfer between fields. Open the output offline and compare every displayed item with its source field.

For a ready-made demonstration, [open the interactive example](research-briefing-dashboard/examples/meeting_brief.html).

## Customising and contributing

See [CUSTOMISING.md](CUSTOMISING.md) for supported configuration keys, deeper source changes, tests, accessibility checks, confidentiality cautions and the ZIP rebuild procedure. See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change. Contributions must use British English and sanitised fixtures only.

## Licences and disclaimer

Software, templates, scripts and implementation structure are available under the [MIT License](LICENSE). Website prose, human-readable documentation, sanitised example prose and `TeX_Live_Codex_Guide.pdf` are available under [CC BY 4.0](CONTENT-LICENSE.md). The downloaded Skill includes standalone copies of both licence notices so that the reuse boundary remains clear after extraction.

This is a personal HDR workflow contribution by Poming Zhang. It is not an official guide of The University of Western Australia, UWA Business School or OpenAI, and it does not imply their endorsement or affiliation. Tool availability varies by environment.
