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
from datetime import datetime
from pathlib import Path, PurePosixPath
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
    "TITLE_EVIDENCE_LINK",
    "EVIDENCE_STATUSLINE",
    "REVIEW_WARNING",
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
EVIDENCE_KEYS = {
    "schema_version",
    "brief_id",
    "review_status",
    "sources",
    "items",
    "issues",
}
EVIDENCE_SOURCE_KEYS = {
    "source_id",
    "display_path",
    "file_type",
    "modified_at",
    "version_status",
    "read_status",
}
EVIDENCE_ITEM_KEYS = {
    "wording_basis",
    "confidence",
    "explicitly_approved",
    "text_sha256",
    "references",
}
EVIDENCE_REFERENCE_KEYS = {
    "source_id",
    "location",
    "relevant_date",
}
EVIDENCE_ISSUE_KEYS = {
    "issue_id",
    "type",
    "description",
    "status",
    "resolution",
    "item_ids",
    "source_ids",
}
EVIDENCE_REVIEW_STATUSES = {"approved", "automatic_unconfirmed"}
EVIDENCE_WORDING_BASES = {
    "directly_stated",
    "conservatively_summarised",
    "inferred",
}
EVIDENCE_CONFIDENCE_LEVELS = {"high", "medium", "low"}
EVIDENCE_VERSION_STATUSES = {
    "single",
    "current",
    "current_candidate",
    "superseded",
    "previous",
    "duplicate",
    "uncertain",
}
EVIDENCE_READ_STATUSES = {"read", "partially_read", "unreadable"}
EVIDENCE_ISSUE_STATUSES = {"open", "resolved", "accepted"}
EVIDENCE_ISSUE_TYPES = {
    "classification_uncertainty",
    "version_conflict",
    "numerical_conflict",
    "interpretation_uncertainty",
    "date_uncertainty",
    "ownership_uncertainty",
    "confidentiality_risk",
    "unsupported_source",
    "other",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
HTTP_URL_IN_TEXT_PATTERN = re.compile(
    r"https?://[^\s<>'\"]+",
    re.IGNORECASE,
)
WINDOWS_PATH_IN_TEXT_PATTERN = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")
UNC_PATH_IN_TEXT_PATTERN = re.compile(
    r"(?<![\w\\])\\\\[^\\/\s]+\\[^\\/\s]+"
)
HOME_RELATIVE_PATH_IN_TEXT_PATTERN = re.compile(
    r"(?<![\w._-])~(?:"
    r"[A-Za-z][A-Za-z0-9._-]*(?=$|[\s,;:)\]}])"
    r"|(?:[A-Za-z0-9._-]+)?[\\/][^\s]+"
    r")"
)
POSIX_LOCAL_PATH_IN_TEXT_PATTERN = re.compile(
    r"(?<![\w._/<~\-])/{1,2}(?!/)[^/\s]+(?:/[^/\s]+)*"
)
ISO_DATE_OR_DATETIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?)?\Z"
)


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


def require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{label} must be an object")
    supplied = set(value)
    missing = sorted(expected - supplied)
    unknown = sorted(supplied - expected)
    issues: list[str] = []
    if missing:
        issues.append("missing key(s): " + ", ".join(missing))
    if unknown:
        issues.append("unknown key(s): " + ", ".join(unknown))
    if issues:
        raise InputError(f"{label} has " + "; ".join(issues))
    return value


def require_non_empty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be non-empty text")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        raise InputError(f"{label} contains a control character")
    return value


def contains_local_path(value: str) -> bool:
    value_without_http_urls = HTTP_URL_IN_TEXT_PATTERN.sub("", value)
    return bool(
        "file://" in value.casefold()
        or WINDOWS_PATH_IN_TEXT_PATTERN.search(value)
        or UNC_PATH_IN_TEXT_PATTERN.search(value)
        or HOME_RELATIVE_PATH_IN_TEXT_PATTERN.search(value)
        or POSIX_LOCAL_PATH_IN_TEXT_PATTERN.search(value_without_http_urls)
    )


def validate_safe_metadata_text(value: Any, label: str) -> str:
    text = require_non_empty_text(value, label)
    if contains_local_path(text):
        raise InputError(f"{label} must not contain a local path or file URL")
    return text


def validate_iso_date_or_datetime(value: Any, label: str) -> str:
    text = validate_safe_metadata_text(value, label)
    if not ISO_DATE_OR_DATETIME_PATTERN.fullmatch(text):
        raise InputError(f"{label} must be an ISO 8601 date or date-time")
    normalised = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise InputError(f"{label} must be a valid ISO 8601 date or date-time") from exc
    return text


def validate_display_path(value: Any, label: str) -> str:
    path = require_non_empty_text(value, label)
    candidate = PurePosixPath(path)
    if (
        candidate.is_absolute()
        or path.startswith("/")
        or "\\" in path
        or "://" in path
        or ".." in candidate.parts
        or candidate.as_posix() in {"", "."}
    ):
        raise InputError(f"{label} must be a safe relative display path")
    return path


def evidence_item_texts(payload: dict[str, Any]) -> dict[str, str]:
    result = {"project_title": payload[PROJECT_TITLE]}
    for field in LIST_FIELDS:
        for index, item in enumerate(payload[field], start=1):
            result[f"{field}-{index}"] = item
    return result


def validate_evidence(payload: Any, content: dict[str, Any]) -> dict[str, Any]:
    evidence = require_exact_keys(payload, EVIDENCE_KEYS, "evidence manifest")
    if evidence["schema_version"] != 1:
        raise InputError("evidence manifest schema_version must be 1")

    expected_brief_id = compute_brief_id(content)
    if evidence["brief_id"] != expected_brief_id:
        raise InputError("evidence manifest brief_id does not match the briefing")
    if evidence["review_status"] not in EVIDENCE_REVIEW_STATUSES:
        raise InputError("evidence manifest review_status is invalid")

    sources = evidence["sources"]
    if not isinstance(sources, list) or not sources:
        raise InputError("evidence manifest sources must be a non-empty array")
    source_identifiers: set[str] = set()
    for index, raw_source in enumerate(sources):
        label = f"evidence source[{index}]"
        source = require_exact_keys(raw_source, EVIDENCE_SOURCE_KEYS, label)
        source_id = require_non_empty_text(source["source_id"], f"{label}.source_id")
        if source_id in source_identifiers:
            raise InputError(f"duplicate evidence source_id: {source_id}")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", source_id) is None:
            raise InputError(f"{label}.source_id has an invalid format")
        source_identifiers.add(source_id)
        validate_display_path(source["display_path"], f"{label}.display_path")
        validate_safe_metadata_text(source["file_type"], f"{label}.file_type")
        if source["modified_at"] is not None:
            validate_iso_date_or_datetime(source["modified_at"], f"{label}.modified_at")
        if source["version_status"] not in EVIDENCE_VERSION_STATUSES:
            raise InputError(f"{label}.version_status is invalid")
        if source["read_status"] not in EVIDENCE_READ_STATUSES:
            raise InputError(f"{label}.read_status is invalid")

    expected_items = evidence_item_texts(content)
    items = evidence["items"]
    if not isinstance(items, dict):
        raise InputError("evidence manifest items must be an object")
    missing_items = sorted(set(expected_items) - set(items))
    unknown_items = sorted(set(items) - set(expected_items))
    if missing_items:
        raise InputError(
            "evidence manifest is missing item provenance: " + ", ".join(missing_items)
        )
    if unknown_items:
        raise InputError(
            "evidence manifest contains unknown item(s): " + ", ".join(unknown_items)
        )

    for item_id, raw_item in items.items():
        label = f"evidence item {item_id}"
        item = require_exact_keys(raw_item, EVIDENCE_ITEM_KEYS, label)
        if item["wording_basis"] not in EVIDENCE_WORDING_BASES:
            raise InputError(f"{label}.wording_basis is invalid")
        if item["confidence"] not in EVIDENCE_CONFIDENCE_LEVELS:
            raise InputError(f"{label}.confidence is invalid")
        if type(item["explicitly_approved"]) is not bool:
            raise InputError(f"{label}.explicitly_approved must be a boolean")
        if (
            item["wording_basis"] == "inferred"
            and evidence["review_status"] == "approved"
            and not item["explicitly_approved"]
        ):
            raise InputError(f"{label} is inferred but was not explicitly approved")
        text_hash = item["text_sha256"]
        if not isinstance(text_hash, str) or SHA256_PATTERN.fullmatch(text_hash) is None:
            raise InputError(f"{label}.text_sha256 must be a lowercase SHA-256 digest")
        expected_hash = hashlib.sha256(expected_items[item_id].encode("utf-8")).hexdigest()
        if text_hash != expected_hash:
            raise InputError(f"{label}.text_sha256 does not match the briefing item")
        references = item["references"]
        if not isinstance(references, list) or not references:
            raise InputError(f"{label}.references must be a non-empty array")
        for reference_index, raw_reference in enumerate(references):
            reference_label = f"{label}.references[{reference_index}]"
            reference = require_exact_keys(
                raw_reference,
                EVIDENCE_REFERENCE_KEYS,
                reference_label,
            )
            source_id = require_non_empty_text(
                reference["source_id"],
                f"{reference_label}.source_id",
            )
            if source_id not in source_identifiers:
                raise InputError(f"{reference_label} uses an unknown source_id")
            validate_safe_metadata_text(
                reference["location"], f"{reference_label}.location"
            )
            if reference["relevant_date"] is not None:
                validate_safe_metadata_text(
                    reference["relevant_date"],
                    f"{reference_label}.relevant_date",
                )

    issues = evidence["issues"]
    if not isinstance(issues, list):
        raise InputError("evidence manifest issues must be an array")
    issue_identifiers: set[str] = set()
    for index, raw_issue in enumerate(issues):
        label = f"evidence issue[{index}]"
        issue = require_exact_keys(raw_issue, EVIDENCE_ISSUE_KEYS, label)
        issue_id = validate_safe_metadata_text(
            issue["issue_id"], f"{label}.issue_id"
        )
        if issue_id in issue_identifiers:
            raise InputError(f"duplicate evidence issue_id: {issue_id}")
        issue_identifiers.add(issue_id)
        if issue["type"] not in EVIDENCE_ISSUE_TYPES:
            raise InputError(f"{label}.type is invalid")
        validate_safe_metadata_text(issue["description"], f"{label}.description")
        if issue["status"] not in EVIDENCE_ISSUE_STATUSES:
            raise InputError(f"{label}.status is invalid")
        if evidence["review_status"] == "approved" and issue["status"] == "open":
            raise InputError(f"{label}.status cannot be open in an approved briefing")
        if (
            evidence["review_status"] == "automatic_unconfirmed"
            and issue["status"] != "open"
        ):
            raise InputError(
                f"{label}.status must be open when review_status is "
                "automatic_unconfirmed"
            )
        validate_safe_metadata_text(issue["resolution"], f"{label}.resolution")
        for collection_name, allowed in (
            ("item_ids", set(expected_items)),
            ("source_ids", source_identifiers),
        ):
            identifiers = issue[collection_name]
            if not isinstance(identifiers, list) or any(
                not isinstance(identifier, str) for identifier in identifiers
            ):
                raise InputError(f"{label}.{collection_name} must be an array of text")
            unknown = sorted(set(identifiers) - allowed)
            if unknown:
                raise InputError(
                    f"{label}.{collection_name} contains unknown identifier(s): "
                    + ", ".join(unknown)
                )

    return evidence


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


def render_evidence_link(item_id: str, evidence: dict[str, Any] | None) -> str:
    if evidence is None:
        return ""
    reference_count = len(evidence["items"][item_id]["references"])
    source_label = "source" if reference_count == 1 else "sources"
    return (
        f'<a class="evidence-link" href="#evidence-item-{item_id}">'
        f"View evidence ({reference_count} {source_label})</a>"
    )


def render_plain_items(
    field: str,
    items: list[str],
    evidence: dict[str, Any] | None,
) -> str:
    if not items:
        return f'<p class="empty-state">{EMPTY_MESSAGE}</p>'
    rendered = "\n".join(
        f'              <li id="briefing-item-{field}-{index}" '
        f'data-briefing-item-id="{field}-{index}">'
        '<span class="source-text">'
        f"{html.escape(item, quote=True)}</span>"
        f"{render_evidence_link(f'{field}-{index}', evidence)}</li>"
        for index, item in enumerate(items, start=1)
    )
    return f'<ul class="item-list">\n{rendered}\n            </ul>'


def render_meeting_item(
    field: str,
    index: int,
    item: str,
    evidence: dict[str, Any] | None,
) -> str:
    item_id = f"{field}-{index}"
    kind = STATE_FIELD_KINDS[field]
    escaped_item = html.escape(item, quote=True)
    note_id = f"{item_id}-note"
    evidence_link = render_evidence_link(item_id, evidence)
    evidence_link_row = (
        f"\n                {evidence_link}" if evidence_link else ""
    )

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

    return f"""              <li class="meeting-item" id="briefing-item-{item_id}" data-briefing-item-id="{item_id}" data-state-id="{item_id}" data-state-kind="{kind}">
                <p class="source-text">{escaped_item}</p>{evidence_link_row}
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
    evidence: dict[str, Any] | None,
) -> str:
    if not items:
        return f'<p class="empty-state">{EMPTY_MESSAGE}</p>'
    if field not in STATE_FIELD_KINDS or not meeting_state_enabled:
        return render_plain_items(field, items, evidence)
    rendered = "\n".join(
        render_meeting_item(field, index, item, evidence)
        for index, item in enumerate(items, start=1)
    )
    return f'<ol class="item-list meeting-list">\n{rendered}\n            </ol>'


def render_field_card(
    field: str,
    items: list[str],
    *,
    meeting_state_enabled: bool,
    evidence: dict[str, Any] | None,
) -> str:
    label = FIELD_LABELS[field]
    return f"""          <section class="section-card" data-field="{field}" aria-labelledby="{field}-heading">
            <h3 id="{field}-heading">{label}</h3>
            {render_items(field, items, meeting_state_enabled=meeting_state_enabled, evidence=evidence)}
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
    evidence: dict[str, Any] | None,
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
                evidence=evidence,
            )
            for field in GROUP_FIELDS[identifier]
        )
    return f"""      <details class="workspace-group" open id="group-{identifier}" data-group="{identifier}">
        <summary><span class="summary-marker" aria-hidden="true"></span><h2 id="group-{identifier}-heading">{label}</h2></summary>
        <div class="group-body">
{body}
        </div>
      </details>"""


def evidence_category(item_id: str) -> str:
    if item_id == "project_title":
        return "project_title"
    for field in LIST_FIELDS:
        if item_id.startswith(field + "-"):
            return field
    raise BuildError(f"Could not determine evidence category for {item_id}")


def evidence_label(identifier: str) -> str:
    if identifier == "project_title":
        return "Project title"
    return FIELD_LABELS[identifier]


def enum_label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def evidence_issue_heading(statuses: set[str]) -> str:
    if statuses == {"accepted"}:
        return "Accepted evidence boundaries"
    if statuses == {"open"}:
        return "Evidence boundaries requiring review"
    if statuses == {"resolved"}:
        return "Resolved evidence issues"
    if statuses == {"accepted", "resolved"}:
        return "Accepted evidence boundaries and resolved issues"
    if statuses == {"open", "resolved"}:
        return "Evidence boundaries requiring review and resolved issues"
    if statuses == {"accepted", "open"}:
        return "Evidence boundaries requiring review and accepted boundaries"
    if statuses == {"accepted", "open", "resolved"}:
        return (
            "Evidence boundaries requiring review, accepted boundaries "
            "and resolved issues"
        )
    return "Evidence boundaries and issue outcomes"


def render_evidence_group(
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    approved_review = evidence["review_status"] == "approved"
    item_text = evidence_item_texts(payload)
    source_lookup = {
        source["source_id"]: source for source in evidence["sources"]
    }
    item_issue_statuses = {
        item_id: {
            issue["status"]
            for issue in evidence["issues"]
            if item_id in issue["item_ids"]
        }
        for item_id in evidence["items"]
    }
    issue_counts = {
        status: sum(
            issue["status"] == status for issue in evidence["issues"]
        )
        for status in EVIDENCE_ISSUE_STATUSES
    }
    if not approved_review and issue_counts["open"]:
        filter_status = "open"
        boundary_filter_label = "Boundaries requiring review only"
    elif issue_counts["accepted"]:
        filter_status = "accepted"
        boundary_filter_label = "Accepted boundaries only"
    else:
        filter_status = None
        boundary_filter_label = "Active boundaries only"
    filter_item_ids = {
        item_id
        for item_id, statuses in item_issue_statuses.items()
        if filter_status in statuses
    }
    basis_counts = {
        basis: sum(
            1
            for item in evidence["items"].values()
            if item["wording_basis"] == basis
        )
        for basis in EVIDENCE_WORDING_BASES
    }
    metrics: list[tuple[str, int]] = [
        ("Approved briefing items" if approved_review else "Briefing items", len(evidence["items"])),
        ("Evidence sources", len(evidence["sources"])),
        ("Directly stated", basis_counts["directly_stated"]),
        ("Conservative summaries", basis_counts["conservatively_summarised"]),
        ("Approved inferences" if approved_review else "Inferences", basis_counts["inferred"]),
    ]
    if issue_counts["open"]:
        metrics.append(("Boundaries requiring review", issue_counts["open"]))
    if issue_counts["accepted"]:
        metrics.append(("Accepted boundaries", issue_counts["accepted"]))
    if issue_counts["resolved"]:
        metrics.append(("Resolved issues", issue_counts["resolved"]))
    metric_html = "\n".join(
        f"""              <div class="count-card">
                <dt>{html.escape(label)}</dt>
                <dd>{count}</dd>
              </div>"""
        for label, count in metrics
    )

    category_options = "\n".join(
        f'<option value="{identifier}">{html.escape(evidence_label(identifier))}</option>'
        for identifier in ("project_title", *LIST_FIELDS)
        if any(
            evidence_category(item_id) == identifier
            for item_id in evidence["items"]
        )
    )
    source_options = "\n".join(
        f'<option value="{html.escape(source["source_id"], quote=True)}">'
        f'{html.escape(source["display_path"])}</option>'
        for source in evidence["sources"]
    )

    record_html: list[str] = []
    for item_id, item in evidence["items"].items():
        category = evidence_category(item_id)
        references = item["references"]
        source_ids = " ".join(reference["source_id"] for reference in references)
        reference_rows = []
        for reference in references:
            source = source_lookup[reference["source_id"]]
            relevant_date = reference["relevant_date"] or "Not supplied"
            reference_rows.append(
                f"""                  <li>
                    <span class="evidence-source-path">{html.escape(source["display_path"])}</span>
                    <span><strong>Location:</strong> {html.escape(reference["location"])}</span>
                    <span><strong>Relevant date:</strong> {html.escape(relevant_date)}</span>
                  </li>"""
            )
        issue_tags = "\n                  ".join(
            f'<span class="uncertainty-tag">{label}</span>'
            for status, label in (
                ("open", "Boundary requiring review"),
                ("accepted", "Accepted boundary"),
                ("resolved", "Resolved issue"),
            )
            if status in item_issue_statuses[item_id]
        )
        issue_tag_rows = f"\n                  {issue_tags}" if issue_tags else ""
        record_html.append(
            f"""            <article class="evidence-record" id="evidence-item-{item_id}" tabindex="-1" data-evidence-record data-category="{category}" data-confidence="{item["confidence"]}" data-basis="{item["wording_basis"]}" data-source-ids="{html.escape(source_ids, quote=True)}" data-uncertain="{'true' if item_id in filter_item_ids else 'false'}">
              <header class="evidence-record-head">
                <div>
                  <p class="evidence-record-id">{html.escape(item_id)}</p>
                  <h3>{html.escape(evidence_label(category))}</h3>
                </div>
                <div class="evidence-tags" aria-label="Evidence status">
                  <span>{html.escape(enum_label(item["wording_basis"]))}</span>
                  <span>{html.escape(enum_label(item["confidence"]))} confidence</span>{issue_tag_rows}
                </div>
              </header>
              <p class="evidence-item-text">{html.escape(item_text[item_id])}</p>
              <details class="evidence-sources">
                <summary>Evidence sources ({len(references)})</summary>
                <ul>
{chr(10).join(reference_rows)}
                </ul>
              </details>
              <a class="return-link" href="#briefing-item-{item_id}">Return to briefing item</a>
            </article>"""
        )

    source_rows = "\n".join(
        f"""                <tr>
                  <th scope="row">{html.escape(source["display_path"])}</th>
                  <td>{html.escape(source["file_type"])}</td>
                  <td>{html.escape(enum_label(source["version_status"]))}</td>
                  <td>{html.escape(enum_label(source["read_status"]))}</td>
                  <td>{html.escape(source["modified_at"] or "Not supplied")}</td>
                </tr>"""
        for source in evidence["sources"]
    )

    if evidence["issues"]:
        issue_html = "\n".join(
            f"""              <article class="evidence-boundary">
                <p class="evidence-record-id">{html.escape(issue["issue_id"])}</p>
                <h3>{html.escape(enum_label(issue["type"]))}</h3>
                <p>{html.escape(issue["description"])}</p>
                <p><strong>{html.escape(enum_label(issue["status"]))}:</strong> {html.escape(issue["resolution"])}</p>
              </article>"""
            for issue in evidence["issues"]
        )
    else:
        issue_html = (
            '<p class="empty-state">No evidence boundaries or issues have been recorded.</p>'
        )

    source_caption = (
        "Approved sources used by this briefing"
        if approved_review
        else "Sources used by this unconfirmed draft"
    )
    boundary_heading = evidence_issue_heading(
        {issue["status"] for issue in evidence["issues"]}
    )

    return f"""      <details class="workspace-group" open id="group-evidence" data-group="evidence" data-evidence-group>
        <summary><span class="summary-marker" aria-hidden="true"></span><h2 id="group-evidence-heading">Evidence Explorer</h2></summary>
        <div class="group-body evidence-group-body">
          <section class="evidence-summary" aria-labelledby="evidence-summary-heading">
            <h3 id="evidence-summary-heading">Evidence summary</h3>
            <dl>
{metric_html}
            </dl>
          </section>
          <section class="evidence-controls" aria-labelledby="evidence-controls-heading">
            <h3 id="evidence-controls-heading">Filter evidence</h3>
            <div class="evidence-control-grid">
              <label>Search evidence<input type="search" id="evidence-search" autocomplete="off"></label>
              <label>Briefing category<select id="evidence-category-filter"><option value="all">All categories</option>{category_options}</select></label>
              <label>Source<select id="evidence-source-filter"><option value="all">All sources</option>{source_options}</select></label>
              <label>Confidence<select id="evidence-confidence-filter"><option value="all">All confidence levels</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
              <label>Wording basis<select id="evidence-basis-filter"><option value="all">All wording bases</option><option value="directly_stated">Directly stated</option><option value="conservatively_summarised">Conservatively summarised</option><option value="inferred">Inferred</option></select></label>
              <label class="checkbox-control"><input type="checkbox" id="evidence-uncertainties-only"{' disabled' if filter_status is None else ''}>{boundary_filter_label}</label>
            </div>
            <div class="evidence-filter-footer">
              <button type="button" id="reset-evidence-filters">Reset evidence filters</button>
              <p id="evidence-result-count" role="status" aria-live="polite"></p>
            </div>
          </section>
          <section class="evidence-results" aria-labelledby="evidence-results-heading">
            <h3 id="evidence-results-heading">Item-level evidence</h3>
{chr(10).join(record_html)}
          </section>
          <section class="evidence-catalogue" aria-labelledby="evidence-catalogue-heading">
            <h3 id="evidence-catalogue-heading">Source catalogue</h3>
            <div class="evidence-table-wrap">
              <table>
                <caption>{source_caption}</caption>
                <thead><tr><th scope="col">Source</th><th scope="col">Type</th><th scope="col">Version</th><th scope="col">Read status</th><th scope="col">Modified</th></tr></thead>
                <tbody>
{source_rows}
                </tbody>
              </table>
            </div>
          </section>
          <section class="evidence-boundaries" aria-labelledby="evidence-boundaries-heading">
            <h3 id="evidence-boundaries-heading">{boundary_heading}</h3>
{issue_html}
          </section>
        </div>
      </details>"""


def render_navigation(
    configuration: dict[str, Any],
    *,
    include_evidence: bool,
) -> tuple[str, str]:
    link_rows = [
        "        <li><a href=\"#group-"
        f"{identifier}\" data-nav-group=\"{identifier}\">"
        f"{html.escape(configuration['group_labels'][identifier], quote=True)}</a></li>"
        for identifier in configuration["group_order"]
    ]
    option_rows = [
        f"          <option value=\"{identifier}\">"
        f"{html.escape(configuration['group_labels'][identifier], quote=True)}</option>"
        for identifier in configuration["group_order"]
    ]
    if include_evidence:
        link_rows.append(
            '        <li><a href="#group-evidence" data-nav-group="evidence">Evidence Explorer</a></li>'
        )
        option_rows.append('          <option value="evidence">Evidence Explorer</option>')
    links = "\n".join(link_rows)
    options = "\n".join(option_rows)
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
    evidence: dict[str, Any] | None = None,
) -> str:
    brief_id = compute_brief_id(payload)
    desktop_navigation, mobile_navigation = render_navigation(
        configuration,
        include_evidence=evidence is not None,
    )
    group_rows = [
        render_group(identifier, payload, configuration, evidence)
        for identifier in configuration["group_order"]
    ]
    if evidence is not None:
        group_rows.append(render_evidence_group(payload, evidence))
    groups = "\n".join(group_rows)
    accent = configuration["theme"]["accent"].lower()
    highlight = configuration["theme"]["highlight"].lower()
    if evidence is None:
        evidence_statusline = ""
    else:
        item_count = len(evidence["items"])
        source_count = len(evidence["sources"])
        review_label = (
            "Approved"
            if evidence["review_status"] == "approved"
            else "Unconfirmed"
        )
        evidence_statusline = (
            '<dl class="evidence-statusline" aria-label="Evidence review status">'
            '<div><dt>Review</dt><dd>'
            + review_label
            + '</dd></div><div><dt>Traceability</dt><dd>Source-grounded review</dd></div>'
            f'<div><dt>Coverage</dt><dd>{item_count} briefing '
            + ("item" if item_count == 1 else "items")
            + f'</dd></div><div><dt>Sources</dt><dd>{source_count} '
            + ("source" if source_count == 1 else "sources")
            + "</dd></div></dl>"
        )
    replacements = {
        "PROJECT_TITLE": html.escape(payload[PROJECT_TITLE], quote=True),
        "TITLE_EVIDENCE_LINK": render_evidence_link("project_title", evidence),
        "EVIDENCE_STATUSLINE": evidence_statusline,
        "REVIEW_WARNING": (
            '<p class="unconfirmed-warning" role="alert"><strong>Unconfirmed draft:</strong> '
            "This briefing was generated without researcher confirmation. Review every item before sharing.</p>"
            if evidence is not None
            and evidence["review_status"] == "automatic_unconfirmed"
            else ""
        ),
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

    renderable_template = template
    for token, value in replacements.items():
        if value != "":
            continue
        renderable_template = re.sub(
            rf"(?m)^[ \t]*\{{\{{{re.escape(token)}\}}\}}[ \t]*(?:\n|\Z)",
            "",
            renderable_template,
        )
    return TOKEN_PATTERN.sub(substitute, renderable_template)


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
        "[--config CONFIG.json] [--evidence EVIDENCE.json]"
    )


def parse_arguments(
    argv: list[str],
) -> tuple[Path, Path, Path | None, Path | None]:
    if len(argv) < 3 or (len(argv) - 3) % 2 != 0:
        raise InputError(usage())
    options: dict[str, Path] = {}
    optional_arguments = argv[3:]
    for index in range(0, len(optional_arguments), 2):
        flag = optional_arguments[index]
        if flag not in {"--config", "--evidence"} or flag in options:
            raise InputError(usage())
        options[flag] = Path(optional_arguments[index + 1])
    return (
        Path(argv[1]),
        Path(argv[2]),
        options.get("--config"),
        options.get("--evidence"),
    )


def main(argv: list[str]) -> int:
    try:
        input_path, output_path, configuration_path, evidence_path = parse_arguments(argv)
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        payload = validate_input(load_json(input_path, "input JSON"))
        configuration = load_configuration(configuration_path)
        evidence = (
            validate_evidence(
                load_json(evidence_path, "evidence manifest JSON"),
                payload,
            )
            if evidence_path is not None
            else None
        )
    except InputError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    except BuildError as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 1

    try:
        template = load_template()
        rendered = render_briefing(payload, configuration, template, evidence)
        atomic_write(output_path, rendered)
    except BuildError as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
