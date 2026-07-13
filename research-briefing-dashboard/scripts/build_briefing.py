#!/usr/bin/env python3
"""Build a self-contained offline supervisor meeting workspace."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = SKILL_ROOT / "assets" / "briefing_template.html"
DEFAULT_CONFIG_PATH = SKILL_ROOT / "config" / "default_config.json"

PROJECT_TITLE = "project_title"
LIST_FIELDS = (
    "recent_progress",
    "completed_work",
    "key_findings",
    "unresolved_questions",
    "decisions_required",
    "next_actions",
    "timeline",
)
REQUIRED_FIELDS = (PROJECT_TITLE, *LIST_FIELDS)
FIELD_LABELS = {
    "recent_progress": "Recent progress",
    "completed_work": "Completed work",
    "key_findings": "Key findings",
    "unresolved_questions": "Unresolved questions",
    "decisions_required": "Decisions required",
    "next_actions": "Next actions",
    "timeline": "Timeline",
}
GROUP_IDENTIFIERS = (
    "overview",
    "progress_evidence",
    "discussion",
    "actions_timeline",
)
GROUP_FIELDS = {
    "overview": (),
    "progress_evidence": (
        "recent_progress",
        "completed_work",
        "key_findings",
    ),
    "discussion": ("unresolved_questions", "decisions_required"),
    "actions_timeline": ("next_actions", "timeline"),
}
STATE_FIELD_KINDS = {
    "unresolved_questions": "question",
    "decisions_required": "decision",
    "next_actions": "action",
}
CONFIG_KEYS = {
    "briefing_label",
    "group_order",
    "group_labels",
    "theme",
    "features",
}
THEME_KEYS = {"accent", "highlight"}
FEATURE_KEYS = {
    "search",
    "counts",
    "collapse_controls",
    "meeting_state",
    "print",
}
HEX_COLOUR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\Z")
EMPTY_MESSAGE = "No items supplied."
TOKEN_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")
EXPECTED_TEMPLATE_TOKENS = {
    "PROJECT_TITLE",
    "BRIEFING_LABEL",
    "BRIEF_ID",
    "ACCENT",
    "ACCENT_FOREGROUND",
    "ACCENT_ON_SURFACE",
    "HIGHLIGHT",
    "HIGHLIGHT_FOREGROUND",
    "HIGHLIGHT_ON_SURFACE",
    "DESKTOP_NAVIGATION",
    "MOBILE_NAVIGATION",
    "WORKSPACE_CONTROLS",
    "GROUPS",
    "FEATURES_JSON",
    "STATE_IDS_JSON",
}


class InputError(ValueError):
    """Report invalid public input without creating output."""


class BuildError(RuntimeError):
    """Report an internal template or output failure."""


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_standard_constant(value: str) -> None:
    raise InputError(f"Invalid JSON constant: {value}")


def load_json(path: Path, description: str) -> Any:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InputError(f"Could not read {description}: {exc}") from exc

    try:
        return json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_standard_constant,
        )
    except InputError:
        raise
    except json.JSONDecodeError as exc:
        raise InputError(
            f"Invalid JSON in {description} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc


def validate_input(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("Top-level input JSON value must be an object.")

    issues: list[str] = []
    supplied = set(payload)
    required = set(REQUIRED_FIELDS)

    missing = sorted(required - supplied)
    if missing:
        issues.append(f"Missing required key(s): {', '.join(missing)}")

    unknown = sorted(supplied - required)
    if unknown:
        issues.append(f"Unknown key(s): {', '.join(unknown)}")

    if PROJECT_TITLE in payload:
        title = payload[PROJECT_TITLE]
        if not isinstance(title, str) or not title.strip():
            issues.append("project_title must be non-empty text")

    for field in LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list):
            issues.append(f"{field} must be an array of non-empty text")
            continue
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                issues.append(f"{field}[{index}] must be non-empty text")

    if issues:
        raise InputError("; ".join(issues))

    return payload


def _missing_keys(
    supplied: set[str],
    required: set[str],
    *,
    partial: bool,
) -> list[str]:
    if partial:
        return []
    return sorted(required - supplied)


def validate_configuration(payload: Any, *, partial: bool) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("Top-level configuration JSON value must be an object.")

    issues: list[str] = []
    supplied = set(payload)
    missing = _missing_keys(supplied, CONFIG_KEYS, partial=partial)
    unknown = sorted(supplied - CONFIG_KEYS)
    if missing:
        issues.append(f"Missing configuration key(s): {', '.join(missing)}")
    if unknown:
        issues.append(f"Unknown configuration key(s): {', '.join(unknown)}")

    if "briefing_label" in payload:
        label = payload["briefing_label"]
        if not isinstance(label, str) or not label.strip():
            issues.append("briefing_label must be non-empty text")

    if "group_order" in payload:
        order = payload["group_order"]
        if (
            not isinstance(order, list)
            or len(order) != len(GROUP_IDENTIFIERS)
            or any(not isinstance(item, str) for item in order)
            or set(order) != set(GROUP_IDENTIFIERS)
        ):
            issues.append(
                "group_order must be an exact permutation of: "
                + ", ".join(GROUP_IDENTIFIERS)
            )

    if "group_labels" in payload:
        labels = payload["group_labels"]
        if not isinstance(labels, dict):
            issues.append("group_labels must be an object")
        else:
            label_keys = set(labels)
            missing_labels = _missing_keys(
                label_keys,
                set(GROUP_IDENTIFIERS),
                partial=partial,
            )
            unknown_labels = sorted(label_keys - set(GROUP_IDENTIFIERS))
            if missing_labels:
                issues.append(
                    "Missing group label(s): " + ", ".join(missing_labels)
                )
            if unknown_labels:
                issues.append(
                    "Unknown group label(s): " + ", ".join(unknown_labels)
                )
            for identifier, value in labels.items():
                if identifier in GROUP_IDENTIFIERS and (
                    not isinstance(value, str) or not value.strip()
                ):
                    issues.append(
                        f"group_labels.{identifier} must be non-empty text"
                    )

    if "theme" in payload:
        theme = payload["theme"]
        if not isinstance(theme, dict):
            issues.append("theme must be an object")
        else:
            theme_keys = set(theme)
            missing_theme = _missing_keys(
                theme_keys,
                THEME_KEYS,
                partial=partial,
            )
            unknown_theme = sorted(theme_keys - THEME_KEYS)
            if missing_theme:
                issues.append(
                    "Missing theme key(s): " + ", ".join(missing_theme)
                )
            if unknown_theme:
                issues.append(
                    "Unknown theme key(s): " + ", ".join(unknown_theme)
                )
            for key, value in theme.items():
                if key in THEME_KEYS and (
                    not isinstance(value, str)
                    or HEX_COLOUR_PATTERN.fullmatch(value) is None
                ):
                    issues.append(
                        f"theme.{key} must be a six-digit hex colour"
                    )

    if "features" in payload:
        features = payload["features"]
        if not isinstance(features, dict):
            issues.append("features must be an object")
        else:
            feature_names = set(features)
            missing_features = _missing_keys(
                feature_names,
                FEATURE_KEYS,
                partial=partial,
            )
            unknown_features = sorted(feature_names - FEATURE_KEYS)
            if missing_features:
                issues.append(
                    "Missing feature key(s): " + ", ".join(missing_features)
                )
            if unknown_features:
                issues.append(
                    "Unknown feature key(s): " + ", ".join(unknown_features)
                )
            for key, value in features.items():
                if key in FEATURE_KEYS and type(value) is not bool:
                    issues.append(f"features.{key} must be a boolean")

    if issues:
        raise InputError("; ".join(issues))
    return payload


def load_configuration(override_path: Path | None) -> dict[str, Any]:
    try:
        defaults = validate_configuration(
            load_json(DEFAULT_CONFIG_PATH, "default configuration JSON"),
            partial=False,
        )
    except InputError as exc:
        raise BuildError(f"Invalid default configuration: {exc}") from exc

    merged = {
        "briefing_label": defaults["briefing_label"],
        "group_order": list(defaults["group_order"]),
        "group_labels": dict(defaults["group_labels"]),
        "theme": dict(defaults["theme"]),
        "features": dict(defaults["features"]),
    }
    if override_path is None:
        return merged

    override = validate_configuration(
        load_json(override_path, "configuration JSON"),
        partial=True,
    )
    for scalar_key in ("briefing_label", "group_order"):
        if scalar_key in override:
            value = override[scalar_key]
            merged[scalar_key] = list(value) if isinstance(value, list) else value
    for object_key in ("group_labels", "theme", "features"):
        if object_key in override:
            merged[object_key].update(override[object_key])
    return merged


def load_template() -> str:
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BuildError(f"Could not read briefing template: {exc}") from exc

    found_tokens = set(TOKEN_PATTERN.findall(template))
    missing_tokens = sorted(EXPECTED_TEMPLATE_TOKENS - found_tokens)
    unknown_tokens = sorted(found_tokens - EXPECTED_TEMPLATE_TOKENS)
    if missing_tokens:
        raise BuildError(
            f"Briefing template is missing token(s): {', '.join(missing_tokens)}"
        )
    if unknown_tokens:
        raise BuildError(
            f"Briefing template has unknown token(s): {', '.join(unknown_tokens)}"
        )
    return template


def compute_brief_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def relative_luminance_for_colour(colour: str) -> float:
    components = [
        int(colour[index : index + 2], 16) / 255
        for index in (1, 3, 5)
    ]

    def linearise(component: float) -> float:
        if component <= 0.04045:
            return component / 12.92
        return ((component + 0.055) / 1.055) ** 2.4

    return sum(
        weight * linearise(component)
        for weight, component in zip((0.2126, 0.7152, 0.0722), components)
    )


def foreground_for_colour(colour: str) -> str:
    luminance = relative_luminance_for_colour(colour)
    black_contrast = (luminance + 0.05) / 0.05
    white_contrast = 1.05 / (luminance + 0.05)
    return "#000000" if black_contrast >= white_contrast else "#ffffff"


def contrast_ratio(first: str, second: str) -> float:
    first_luminance = relative_luminance_for_colour(first)
    second_luminance = relative_luminance_for_colour(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def surface_colour_for(colour: str) -> str:
    """Preserve the configured hue while meeting WCAG contrast on light panels."""

    original = tuple(
        int(colour[index : index + 2], 16)
        for index in (1, 3, 5)
    )
    for scale in range(255, -1, -1):
        components = tuple(
            round(component * scale / 255)
            for component in original
        )
        candidate = "#" + "".join(
            f"{component:02x}" for component in components
        )
        if all(
            contrast_ratio(candidate, surface) >= 4.5
            for surface in ("#ffffff", "#f7f9fa")
        ):
            return candidate
    return "#000000"


def render_plain_items(items: list[str]) -> str:
    if not items:
        return f'<p class="empty-state">{EMPTY_MESSAGE}</p>'
    rendered = "\n".join(
        "              <li><span class=\"source-text\">"
        f"{html.escape(item, quote=True)}</span></li>"
        for item in items
    )
    return f'<ul class="item-list">\n{rendered}\n            </ul>'


def render_meeting_item(field: str, index: int, item: str) -> str:
    item_id = f"{field}-{index}"
    kind = STATE_FIELD_KINDS[field]
    escaped_item = html.escape(item, quote=True)
    note_id = f"{item_id}-note"

    if kind == "question":
        status_control = f"""<div class="status-field">
                    <input type="checkbox" id="{item_id}-discussed" data-state-control="discussed">
                    <label for="{item_id}-discussed">Discussed</label>
                  </div>"""
    elif kind == "decision":
        status_control = f"""<div class="status-field select-field">
                    <label for="{item_id}-status">Decision status</label>
                    <select id="{item_id}-status" data-state-control="status">
                      <option value="pending">Pending</option>
                      <option value="agreed">Agreed</option>
                      <option value="deferred">Deferred</option>
                    </select>
                  </div>"""
    else:
        status_control = f"""<div class="status-field">
                    <input type="checkbox" id="{item_id}-completed" data-state-control="completed">
                    <label for="{item_id}-completed">Completed</label>
                  </div>"""

    return f"""              <li class="meeting-item" data-state-id="{item_id}" data-state-kind="{kind}">
                <p class="source-text">{escaped_item}</p>
                <div class="meeting-item-controls">
                  {status_control}
                  <div class="note-field">
                    <label for="{note_id}">Meeting note</label>
                    <textarea id="{note_id}" data-state-control="note" maxlength="5000" rows="3"></textarea>
                  </div>
                </div>
                <p class="print-state" aria-hidden="true"></p>
              </li>"""


def render_items(
    field: str,
    items: list[str],
    *,
    meeting_state_enabled: bool,
) -> str:
    if not items:
        return f'<p class="empty-state">{EMPTY_MESSAGE}</p>'
    if field not in STATE_FIELD_KINDS or not meeting_state_enabled:
        return render_plain_items(items)
    rendered = "\n".join(
        render_meeting_item(field, index, item)
        for index, item in enumerate(items, start=1)
    )
    return f'<ol class="item-list meeting-list">\n{rendered}\n            </ol>'


def render_field_card(
    field: str,
    items: list[str],
    *,
    meeting_state_enabled: bool,
) -> str:
    label = FIELD_LABELS[field]
    return f"""          <section class="section-card" data-field="{field}" aria-labelledby="{field}-heading">
            <h3 id="{field}-heading">{label}</h3>
            {render_items(field, items, meeting_state_enabled=meeting_state_enabled)}
          </section>"""


def render_overview_counts(payload: dict[str, Any]) -> str:
    counts = "\n".join(
        f"""              <div class="count-card" data-count="{len(payload[field])}">
                <dt>{FIELD_LABELS[field]}</dt>
                <dd>{len(payload[field])}</dd>
              </div>"""
        for field in LIST_FIELDS
    )
    return f"""        <section id="overview-counts" class="overview-counts" aria-labelledby="overview-counts-heading">
          <h3 id="overview-counts-heading">Content counts</h3>
          <dl>
{counts}
          </dl>
        </section>"""


def render_group(
    identifier: str,
    payload: dict[str, Any],
    configuration: dict[str, Any],
) -> str:
    label = html.escape(configuration["group_labels"][identifier], quote=True)
    if identifier == "overview":
        body = (
            render_overview_counts(payload)
            if configuration["features"]["counts"]
            else ""
        )
    else:
        body = "\n".join(
            render_field_card(
                field,
                payload[field],
                meeting_state_enabled=configuration["features"]["meeting_state"],
            )
            for field in GROUP_FIELDS[identifier]
        )
    return f"""      <details class="workspace-group" open id="group-{identifier}" data-group="{identifier}">
        <summary><span class="summary-marker" aria-hidden="true"></span><h2 id="group-{identifier}-heading">{label}</h2></summary>
        <div class="group-body">
{body}
        </div>
      </details>"""


def render_navigation(configuration: dict[str, Any]) -> tuple[str, str]:
    links = "\n".join(
        "        <li><a href=\"#group-"
        f"{identifier}\" data-nav-group=\"{identifier}\">"
        f"{html.escape(configuration['group_labels'][identifier], quote=True)}</a></li>"
        for identifier in configuration["group_order"]
    )
    options = "\n".join(
        f"          <option value=\"{identifier}\">"
        f"{html.escape(configuration['group_labels'][identifier], quote=True)}</option>"
        for identifier in configuration["group_order"]
    )
    desktop = f"""      <nav class="sidebar-nav" aria-label="Briefing sections">
        <h2>Meeting workspace</h2>
        <ul>
{links}
        </ul>
      </nav>"""
    mobile = f"""    <nav class="mobile-nav" aria-label="Briefing sections on small screens">
      <label for="mobile-group-nav">Go to section</label>
      <select id="mobile-group-nav">
{options}
      </select>
    </nav>"""
    return desktop, mobile


def render_workspace_controls(configuration: dict[str, Any]) -> str:
    features = configuration["features"]
    controls: list[str] = []
    if features["search"]:
        controls.append(
            """      <div class="search-control">
        <label for="workspace-search">Search briefing</label>
        <input type="search" id="workspace-search" autocomplete="off" spellcheck="false">
      </div>"""
        )
    action_buttons: list[str] = []
    if features["collapse_controls"]:
        action_buttons.extend(
            (
                '<button type="button" id="expand-all">Expand all</button>',
                '<button type="button" id="collapse-all">Collapse all</button>',
            )
        )
    if features["print"]:
        action_buttons.append(
            '<button type="button" id="print-briefing" class="emphasised-control">Print</button>'
        )
    if action_buttons:
        controls.append(
            '      <div class="workspace-button-group" aria-label="Workspace display controls">\n'
            + "\n".join(f"        {button}" for button in action_buttons)
            + "\n      </div>"
        )
    if features["meeting_state"]:
        controls.append(
            """      <div class="workspace-button-group state-button-group" aria-label="Meeting state controls">
        <button type="button" id="export-state">Export state</button>
        <input type="file" id="import-state" accept="application/json,.json">
        <label for="import-state" class="button-label">Import state</label>
        <button type="button" id="reset-state">Reset state</button>
        <p class="state-confidentiality-warning"><strong>Confidentiality:</strong> Exported meeting-state files may contain confidential material. They remain on this device. They are not uploaded by this workspace.</p>
        <p id="state-message" class="state-message" role="status" aria-live="polite"></p>
      </div>"""
        )
    if not controls:
        return ""
    return '<section class="workspace-tools" aria-label="Meeting workspace tools">\n' + (
        "\n".join(controls)
    ) + "\n    </section>"


def state_ids(payload: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "questions": [
            f"unresolved_questions-{index}"
            for index in range(1, len(payload["unresolved_questions"]) + 1)
        ],
        "decisions": [
            f"decisions_required-{index}"
            for index in range(1, len(payload["decisions_required"]) + 1)
        ],
        "actions": [
            f"next_actions-{index}"
            for index in range(1, len(payload["next_actions"]) + 1)
        ],
    }


def render_briefing(
    payload: dict[str, Any],
    configuration: dict[str, Any],
    template: str,
) -> str:
    brief_id = compute_brief_id(payload)
    desktop_navigation, mobile_navigation = render_navigation(configuration)
    groups = "\n".join(
        render_group(identifier, payload, configuration)
        for identifier in configuration["group_order"]
    )
    accent = configuration["theme"]["accent"].lower()
    highlight = configuration["theme"]["highlight"].lower()
    replacements = {
        "PROJECT_TITLE": html.escape(payload[PROJECT_TITLE], quote=True),
        "BRIEFING_LABEL": html.escape(
            configuration["briefing_label"], quote=True
        ),
        "BRIEF_ID": brief_id,
        "ACCENT": accent,
        "ACCENT_FOREGROUND": foreground_for_colour(accent),
        "ACCENT_ON_SURFACE": surface_colour_for(accent),
        "HIGHLIGHT": highlight,
        "HIGHLIGHT_FOREGROUND": foreground_for_colour(highlight),
        "HIGHLIGHT_ON_SURFACE": surface_colour_for(highlight),
        "DESKTOP_NAVIGATION": desktop_navigation,
        "MOBILE_NAVIGATION": mobile_navigation,
        "WORKSPACE_CONTROLS": render_workspace_controls(configuration),
        "GROUPS": groups,
        "FEATURES_JSON": json.dumps(
            configuration["features"],
            sort_keys=True,
            separators=(",", ":"),
        ),
        "STATE_IDS_JSON": json.dumps(
            state_ids(payload),
            sort_keys=True,
            separators=(",", ":"),
        ),
    }

    def substitute(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in replacements:
            raise BuildError(f"Unresolved template token: {match.group(0)}")
        return replacements[token]

    return TOKEN_PATTERN.sub(substitute, template)


def atomic_write(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(
            file_descriptor,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise BuildError(f"Could not write output HTML: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def usage() -> str:
    return (
        "Usage: python3 scripts/build_briefing.py INPUT.json OUTPUT.html "
        "[--config CONFIG.json]"
    )


def parse_arguments(argv: list[str]) -> tuple[Path, Path, Path | None]:
    if len(argv) == 3:
        return Path(argv[1]), Path(argv[2]), None
    if len(argv) == 5 and argv[3] == "--config":
        return Path(argv[1]), Path(argv[2]), Path(argv[4])
    raise InputError(usage())


def main(argv: list[str]) -> int:
    try:
        input_path, output_path, configuration_path = parse_arguments(argv)
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        payload = validate_input(load_json(input_path, "input JSON"))
        configuration = load_configuration(configuration_path)
    except InputError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    except BuildError as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 1

    try:
        template = load_template()
        rendered = render_briefing(payload, configuration, template)
        atomic_write(output_path, rendered)
    except BuildError as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
