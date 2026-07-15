#!/usr/bin/env python3
"""Contract tests for the offline supervisor meeting workspace builder."""

from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
BUILDER = SKILL_ROOT / "scripts" / "build_briefing.py"
DEFAULT_CONFIG = SKILL_ROOT / "config" / "default_config.json"
LIST_FIELDS = (
    "recent_progress",
    "completed_work",
    "key_findings",
    "unresolved_questions",
    "decisions_required",
    "next_actions",
    "timeline",
)
FIELD_LABELS = {
    "recent_progress": "Recent progress",
    "completed_work": "Completed work",
    "key_findings": "Key findings",
    "unresolved_questions": "Unresolved questions",
    "decisions_required": "Decisions required",
    "next_actions": "Next actions",
    "timeline": "Timeline",
}


def valid_payload() -> dict[str, Any]:
    return {
        "project_title": "Accessible research diaries",
        "recent_progress": ["Completed participant follow-up."],
        "completed_work": ["Cleaned the interview transcripts."],
        "key_findings": ["Diary completion remained consistent."],
        "unresolved_questions": ["Should the coding frame be extended?"],
        "decisions_required": ["Agree the next analysis checkpoint."],
        "next_actions": ["Draft the revised coding frame."],
        "timeline": ["Review the draft at the next meeting."],
    }


def relative_luminance(colour: str) -> float:
    components = [
        int(colour[index : index + 2], 16) / 255
        for index in (1, 3, 5)
    ]

    def linearise(component: float) -> float:
        if component <= 0.04045:
            return component / 12.92
        return ((component + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearise(component) for component in components)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    first_luminance = relative_luminance(first)
    second_luminance = relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


class BriefingBuilderTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.work = Path(self.temporary_directory.name)

    def write_json(self, name: str, value: Any) -> Path:
        path = self.work / name
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def run_builder(
        self,
        payload: dict[str, Any] | None = None,
        *,
        config: Any | None = None,
        evidence: Any | None = None,
        output_name: str = "briefing.html",
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        input_path = self.write_json("input.json", payload or valid_payload())
        output_path = self.work / output_name
        command = [sys.executable, str(BUILDER), str(input_path), str(output_path)]
        if config is not None:
            config_path = self.write_json("config.json", config)
            command.extend(["--config", str(config_path)])
        if evidence is not None:
            evidence_path = self.write_json("evidence.json", evidence)
            command.extend(["--evidence", str(evidence_path)])
        result = subprocess.run(
            command,
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, output_path

    def build_html(
        self,
        payload: dict[str, Any] | None = None,
        *,
        config: Any | None = None,
        evidence: Any | None = None,
        output_name: str = "briefing.html",
    ) -> str:
        result, output_path = self.run_builder(
            payload,
            config=config,
            evidence=evidence,
            output_name=output_name,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        return output_path.read_text(encoding="utf-8")

    def assert_rejected_without_output_change(
        self,
        *,
        payload: dict[str, Any] | None = None,
        config: Any | None = None,
        evidence: Any | None = None,
    ) -> None:
        output_path = self.work / "briefing.html"
        output_path.write_text("existing output", encoding="utf-8")
        result, returned_path = self.run_builder(
            payload,
            config=config,
            evidence=evidence,
        )
        self.assertEqual(returned_path, output_path)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("error", result.stderr.lower())
        self.assertEqual(output_path.read_text(encoding="utf-8"), "existing output")

    def valid_evidence(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        content = payload or valid_payload()
        brief_id = hashlib.sha256(
            json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        source = {
            "source_id": "source-001",
            "display_path": "notes/progress_note.md",
            "file_type": "Markdown",
            "modified_at": "2026-07-14",
            "version_status": "current",
            "read_status": "read",
        }
        items: dict[str, Any] = {
            "project_title": {
                "wording_basis": "conservatively_summarised",
                "confidence": "high",
                "explicitly_approved": True,
                "text_sha256": hashlib.sha256(
                    content["project_title"].encode("utf-8")
                ).hexdigest(),
                "references": [
                    {
                        "source_id": "source-001",
                        "location": "heading: Project title",
                        "relevant_date": "2026-07-14",
                    }
                ],
            }
        }
        for field in LIST_FIELDS:
            for index, item_text in enumerate(content[field], start=1):
                items[f"{field}-{index}"] = {
                    "wording_basis": "directly_stated",
                    "confidence": "high",
                    "explicitly_approved": True,
                    "text_sha256": hashlib.sha256(
                        item_text.encode("utf-8")
                    ).hexdigest(),
                    "references": [
                        {
                            "source_id": "source-001",
                            "location": f"heading: {FIELD_LABELS[field]}",
                            "relevant_date": "2026-07-14",
                        }
                    ],
                }
        return {
            "schema_version": 1,
            "brief_id": brief_id,
            "review_status": "approved",
            "sources": [source],
            "items": items,
            "issues": [
                {
                    "issue_id": "issue-001",
                    "type": "classification_uncertainty",
                    "description": "The researcher retained one classification boundary.",
                    "status": "accepted",
                    "resolution": "Discuss the boundary with supervisors.",
                    "item_ids": ["unresolved_questions-1"],
                    "source_ids": ["source-001"],
                }
            ],
        }

    def test_legacy_two_positional_argument_command_still_builds(self) -> None:
        result, output_path = self.run_builder()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output_path.is_file())
        generated = output_path.read_text(encoding="utf-8")
        self.assertIn('lang="en-GB"', generated)
        self.assertIn('<link rel="icon" href="data:,">', generated)
        self.assertIn("Accessible research diaries", generated)
        for field_value in valid_payload().values():
            if isinstance(field_value, list):
                for item in field_value:
                    self.assertIn(item, generated)

    def test_default_configuration_file_has_the_published_contract(self) -> None:
        expected = {
            "briefing_label": "Supervisor meeting briefing",
            "group_order": [
                "overview",
                "progress_evidence",
                "discussion",
                "actions_timeline",
            ],
            "group_labels": {
                "overview": "Overview",
                "progress_evidence": "Progress and evidence",
                "discussion": "Discussion workspace",
                "actions_timeline": "Actions and timeline",
            },
            "theme": {"accent": "#0f5c5e", "highlight": "#b56a00"},
            "features": {
                "search": True,
                "counts": True,
                "collapse_controls": True,
                "meeting_state": True,
                "print": True,
            },
        }

        self.assertTrue(DEFAULT_CONFIG.is_file())
        self.assertEqual(
            json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8")),
            expected,
        )

    def test_partial_configuration_deep_merges_and_reorders_groups(self) -> None:
        config = {
            "briefing_label": "Doctoral review workspace",
            "group_order": [
                "discussion",
                "overview",
                "actions_timeline",
                "progress_evidence",
            ],
            "group_labels": {"discussion": "Questions and decisions"},
            "theme": {"accent": "#ffffff", "highlight": "#000000"},
            "features": {"search": False},
        }

        generated = self.build_html(config=config)

        self.assertIn("Doctoral review workspace", generated)
        self.assertIn("Questions and decisions", generated)
        self.assertIn("Progress and evidence", generated)
        positions = [
            generated.index(f'id="group-{identifier}"')
            for identifier in config["group_order"]
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("--accent: #ffffff;", generated)
        self.assertIn("--accent-foreground: #000000;", generated)
        self.assertIn("--highlight: #000000;", generated)
        self.assertIn("--highlight-foreground: #ffffff;", generated)
        self.assertNotIn('id="workspace-search"', generated)
        self.assertIn('id="overview-counts"', generated)

    def test_extreme_theme_colours_have_safe_surface_tokens_and_focus(self) -> None:
        for accent, highlight in (
            ("#ffffff", "#000000"),
            ("#000000", "#ffffff"),
        ):
            with self.subTest(accent=accent, highlight=highlight):
                generated = self.build_html(
                    config={"theme": {"accent": accent, "highlight": highlight}},
                    output_name=f"extreme-{accent[1]}-{highlight[1]}.html",
                )

                surface_tokens = {}
                for name in ("accent-on-surface", "highlight-on-surface"):
                    match = re.search(rf"--{name}: (#[0-9a-f]{{6}});", generated)
                    self.assertIsNotNone(match, name)
                    surface_tokens[name] = match.group(1)
                    for surface in ("#ffffff", "#f7f9fa"):
                        self.assertGreaterEqual(
                            contrast_ratio(surface_tokens[name], surface),
                            4.5,
                            f"{name} against {surface}",
                        )

                for raw_token in ("accent", "highlight"):
                    properties = re.findall(
                        rf"([a-z-]+):[^;{{}}]*var\(--{raw_token}\);",
                        generated,
                    )
                    self.assertTrue(properties, raw_token)
                    self.assertEqual(set(properties), {"background"})

                self.assertGreaterEqual(
                    generated.count("var(--accent-on-surface)"),
                    8,
                )
                self.assertGreaterEqual(
                    generated.count("var(--highlight-on-surface)"),
                    1,
                )
                self.assertIn("--focus-inner: #ffffff;", generated)
                self.assertIn("--focus-outer: #000000;", generated)
                self.assertIn(
                    "outline: 0.2rem solid var(--focus-inner);",
                    generated,
                )
                self.assertIn(
                    "box-shadow: 0 0 0 0.4rem var(--focus-outer);",
                    generated,
                )

    def test_state_confidentiality_warning_and_neutral_footer_are_accurate(self) -> None:
        generated = self.build_html()
        disabled = self.build_html(
            config={"features": {"meeting_state": False}},
            output_name="without-state.html",
        )
        footer = (
            '<p>This self-contained briefing works offline and was generated '
            "from supplied notes only.</p>"
        )

        self.assertIn('class="state-confidentiality-warning"', generated)
        self.assertIn(
            "Exported meeting-state files may contain confidential material.",
            generated,
        )
        self.assertIn("They are not uploaded by this workspace.", generated)
        self.assertNotIn('class="state-confidentiality-warning"', disabled)
        self.assertIn(footer, generated)
        self.assertIn(footer, disabled)
        self.assertNotIn("browser session unless exported", generated)

    def test_invalid_configuration_variants_exit_two_atomically(self) -> None:
        invalid_configs = {
            "non-object": [],
            "unknown top-level key": {"extra": True},
            "blank briefing label": {"briefing_label": "  "},
            "wrong briefing label type": {"briefing_label": 1},
            "incomplete group order": {"group_order": ["overview"]},
            "duplicate group order": {
                "group_order": [
                    "overview",
                    "overview",
                    "discussion",
                    "actions_timeline",
                ]
            },
            "unknown group order value": {
                "group_order": [
                    "overview",
                    "progress_evidence",
                    "discussion",
                    "other",
                ]
            },
            "wrong group labels type": {"group_labels": []},
            "unknown group label": {"group_labels": {"other": "Other"}},
            "blank group label": {"group_labels": {"overview": ""}},
            "wrong theme type": {"theme": "dark"},
            "unknown theme key": {"theme": {"background": "#ffffff"}},
            "short colour": {"theme": {"accent": "#fff"}},
            "non-hex colour": {"theme": {"highlight": "#gg0000"}},
            "wrong features type": {"features": []},
            "unknown feature": {"features": {"sharing": True}},
            "integer feature": {"features": {"search": 1}},
            "string feature": {"features": {"print": "yes"}},
        }

        for label, config in invalid_configs.items():
            with self.subTest(label=label):
                self.assert_rejected_without_output_change(config=config)

    def test_duplicate_configuration_keys_are_rejected_atomically(self) -> None:
        input_path = self.write_json("input.json", valid_payload())
        config_path = self.work / "config.json"
        config_path.write_text(
            '{"features":{"search":true,"search":false}}',
            encoding="utf-8",
        )
        output_path = self.work / "briefing.html"
        output_path.write_text("existing output", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                str(input_path),
                str(output_path),
                "--config",
                str(config_path),
            ],
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Duplicate JSON key", result.stderr)
        self.assertEqual(output_path.read_text(encoding="utf-8"), "existing output")

    def test_content_contract_rejections_remain_atomic(self) -> None:
        invalid_payloads = {
            "unknown key": {**valid_payload(), "owner": "Researcher"},
            "missing key": {
                key: value
                for key, value in valid_payload().items()
                if key != "timeline"
            },
            "blank title": {**valid_payload(), "project_title": "\t"},
            "wrong list type": {**valid_payload(), "recent_progress": "Done"},
            "blank list item": {**valid_payload(), "key_findings": [" "]},
            "boolean list item": {**valid_payload(), "next_actions": [True]},
        }

        for label, payload in invalid_payloads.items():
            with self.subTest(label=label):
                self.assert_rejected_without_output_change(payload=payload)

    def test_duplicate_content_keys_remain_rejected_atomically(self) -> None:
        input_path = self.work / "input.json"
        input_path.write_text(
            """{
              "project_title": "First",
              "project_title": "Second",
              "recent_progress": [],
              "completed_work": [],
              "key_findings": [],
              "unresolved_questions": [],
              "decisions_required": [],
              "next_actions": [],
              "timeline": []
            }""",
            encoding="utf-8",
        )
        output_path = self.work / "briefing.html"
        output_path.write_text("existing output", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(BUILDER), str(input_path), str(output_path)],
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Duplicate JSON key", result.stderr)
        self.assertEqual(output_path.read_text(encoding="utf-8"), "existing output")

    def test_brief_id_is_canonical_and_configuration_independent(self) -> None:
        payload = valid_payload()
        first = self.build_html(payload, output_name="first.html")
        second = self.build_html(
            payload,
            config={
                "briefing_label": "Alternative label",
                "group_order": [
                    "actions_timeline",
                    "discussion",
                    "progress_evidence",
                    "overview",
                ],
                "theme": {"accent": "#112233"},
            },
            output_name="second.html",
        )
        expected = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        first_id = re.search(r'data-brief-id="([0-9a-f]{64})"', first)
        second_id = re.search(r'data-brief-id="([0-9a-f]{64})"', second)
        self.assertIsNotNone(first_id)
        self.assertIsNotNone(second_id)
        self.assertEqual(first_id.group(1), expected)
        self.assertEqual(second_id.group(1), expected)

    def test_supplied_content_and_configuration_text_are_escaped(self) -> None:
        payload = valid_payload()
        payload["project_title"] = '<script>alert("title")</script>'
        payload["recent_progress"] = [
            '<img src=x onerror="alert(1)"> & a completed task'
        ]
        config = {
            "briefing_label": '<svg onload="alert(2)">',
            "group_labels": {"overview": '<b data-test="label">Overview</b>'},
        }

        generated = self.build_html(payload, config=config)

        self.assertNotIn("<script>alert", generated)
        self.assertNotIn("<img src=x", generated)
        self.assertNotIn("<svg onload", generated)
        self.assertNotIn('<b data-test="label">', generated)
        self.assertIn(html.escape(payload["project_title"], quote=True), generated)
        self.assertIn(
            html.escape(payload["recent_progress"][0], quote=True),
            generated,
        )
        self.assertIn(html.escape(config["briefing_label"], quote=True), generated)
        self.assertIn(
            html.escape(config["group_labels"]["overview"], quote=True),
            generated,
        )

    def test_empty_arrays_render_the_exact_empty_message(self) -> None:
        payload = valid_payload()
        for key in payload:
            if key != "project_title":
                payload[key] = []

        generated = self.build_html(payload)

        self.assertEqual(generated.count("No items supplied."), 7)
        self.assertEqual(generated.count('data-count="0"'), 7)

    def test_all_groups_semantic_fields_and_default_controls_are_present(self) -> None:
        generated = self.build_html()

        self.assertIn('<a class="skip-link" href="#main-content">', generated)
        self.assertIn('<header class="masthead">', generated)
        self.assertIn('<main id="main-content"', generated)
        self.assertIn('<nav class="sidebar-nav"', generated)
        self.assertIn('<nav class="mobile-nav"', generated)
        self.assertIn('<footer class="document-footer">', generated)
        for identifier in (
            "overview",
            "progress_evidence",
            "discussion",
            "actions_timeline",
        ):
            self.assertIn(f'id="group-{identifier}"', generated)
            self.assertIn(f'data-group="{identifier}"', generated)
        expected_group_fields = {
            "progress_evidence": (
                "recent_progress",
                "completed_work",
                "key_findings",
            ),
            "discussion": ("unresolved_questions", "decisions_required"),
            "actions_timeline": ("next_actions", "timeline"),
        }
        for group, fields in expected_group_fields.items():
            start = generated.index(f'id="group-{group}"')
            later_groups = [
                generated.find(
                    '<details class="workspace-group" open id="group-',
                    start + 1,
                ),
                generated.find("</details>", start),
            ]
            ends = [position for position in later_groups if position >= 0]
            end = min(ends) if ends else len(generated)
            group_html = generated[start:end]
            for field in fields:
                self.assertIn(f'data-field="{field}"', group_html)
        for control_id in (
            "workspace-search",
            "expand-all",
            "collapse-all",
            "print-briefing",
            "export-state",
            "import-state",
            "reset-state",
        ):
            self.assertIn(f'id="{control_id}"', generated)
        self.assertLess(
            generated.index('<input type="file" id="import-state"'),
            generated.index('<label for="import-state" class="button-label">'),
        )
        self.assertIn('id="overview-counts"', generated)
        self.assertIn("@media (prefers-reduced-motion: reduce)", generated)
        self.assertIn("@page", generated)
        self.assertIn("size: A4", generated)
        self.assertIn(":focus-visible", generated)

    def test_feature_flags_remove_only_their_optional_interface(self) -> None:
        generated = self.build_html(
            config={
                "features": {
                    "search": False,
                    "counts": False,
                    "collapse_controls": False,
                    "meeting_state": False,
                    "print": False,
                }
            }
        )

        for control_id in (
            "workspace-search",
            "overview-counts",
            "expand-all",
            "collapse-all",
            "print-briefing",
            "export-state",
            "import-state",
            "reset-state",
        ):
            self.assertNotIn(f'id="{control_id}"', generated)
        self.assertNotIn('class="meeting-item-controls"', generated)
        for identifier in (
            "overview",
            "progress_evidence",
            "discussion",
            "actions_timeline",
        ):
            self.assertIn(f'id="group-{identifier}"', generated)
        for value in valid_payload().values():
            if isinstance(value, list):
                for item in value:
                    self.assertIn(item, generated)

    def test_output_has_no_external_dependencies_storage_or_template_tokens(self) -> None:
        generated = self.build_html()

        self.assertNotRegex(
            generated,
            re.compile(r'(?:src|href)=["\'](?:https?:)?//', re.IGNORECASE),
        )
        self.assertNotRegex(generated, re.compile(r"@import\b", re.IGNORECASE))
        self.assertNotIn("localStorage", generated)
        self.assertNotIn("sessionStorage", generated)
        self.assertNotRegex(generated, re.compile(r"\{\{[A-Z0-9_]+\}\}"))
        self.assertFalse(
            any(line.rstrip() != line for line in generated.splitlines()),
            "Generated HTML must not contain trailing whitespace",
        )

    def test_multiline_research_text_preserves_trailing_whitespace_exactly(self) -> None:
        payload = valid_payload()
        supplied = "Markdown hard break  \nTabbed spacing\t \nFinal line"
        payload["recent_progress"] = [supplied]

        generated = self.build_html(payload)

        self.assertIn(html.escape(supplied, quote=True), generated)

    def test_optional_evidence_markup_does_not_leave_indentation_only_lines(self) -> None:
        generated = self.build_html(evidence=self.valid_evidence())

        self.assertFalse(
            any(line.rstrip() != line for line in generated.splitlines()),
            "Optional evidence markup must not leave trailing whitespace",
        )

    def test_meeting_state_contract_constants_ids_and_atomic_apply_are_embedded(self) -> None:
        payload = valid_payload()
        payload["unresolved_questions"].append("Is a second coder required?")
        payload["decisions_required"].append("Choose the reporting structure.")
        payload["next_actions"].append("Prepare the reliability table.")

        generated = self.build_html(payload)

        self.assertIn("const SCHEMA_VERSION = 1;", generated)
        self.assertIn("const MAX_IMPORT_BYTES = 262144;", generated)
        self.assertIn("const MAX_NOTE_CODE_POINTS = 5000;", generated)
        self.assertIn('const STATE_FILENAME = "supervisor-meeting-state.json";', generated)
        for item_id in (
            "unresolved_questions-1",
            "unresolved_questions-2",
            "decisions_required-1",
            "decisions_required-2",
            "next_actions-1",
            "next_actions-2",
        ):
            self.assertIn(f'data-state-id="{item_id}"', generated)
        for key in (
            "schema_version",
            "brief_id",
            "exported_at",
            "questions",
            "decisions",
            "actions",
        ):
            self.assertIn(f'"{key}"', generated)
        self.assertIn("const validatedState = validateImportedState(candidate);", generated)
        self.assertIn("applyMeetingState(validatedState);", generated)
        self.assertLess(
            generated.index("const validatedState = validateImportedState(candidate);"),
            generated.index("applyMeetingState(validatedState);"),
        )
        self.assertIn('message.setAttribute("role", "alert")', generated)
        self.assertNotIn('"project_title"', generated)

    def test_progressive_enhancement_and_print_state_markers_are_present(self) -> None:
        generated = self.build_html()

        self.assertEqual(generated.count("<details class=\"workspace-group\""), 4)
        self.assertEqual(generated.count("<details class=\"workspace-group\" open"), 4)
        self.assertIn('document.documentElement.classList.add("js")', generated)
        self.assertIn("scroll-behavior: smooth", generated)
        self.assertIn("beforeprint", generated)
        self.assertIn("afterprint", generated)
        self.assertIn('class="print-state"', generated)
        self.assertIn("@media print", generated)
        self.assertIn(".workspace-navigation", generated)
        self.assertIn("display: none", generated)

    def test_optional_evidence_manifest_renders_linked_explorer(self) -> None:
        evidence = self.valid_evidence()

        generated = self.build_html(evidence=evidence)

        self.assertEqual(generated.count('<details class="workspace-group"'), 5)
        self.assertIn('id="group-evidence"', generated)
        self.assertIn("page-break-inside: avoid;", generated)
        self.assertIn(".evidence-sources > summary::marker", generated)
        self.assertIn("break-after: avoid;", generated)
        self.assertIn("Evidence Explorer", generated)
        self.assertIn("Evidence sources", generated)
        self.assertIn("Filter evidence", generated)
        self.assertIn('id="evidence-category-filter"', generated)
        self.assertIn('id="evidence-source-filter"', generated)
        self.assertIn('id="evidence-confidence-filter"', generated)
        self.assertIn('id="evidence-basis-filter"', generated)
        self.assertIn('id="evidence-uncertainties-only"', generated)
        self.assertIn('class="evidence-link"', generated)
        self.assertIn("View evidence", generated)
        self.assertIn("notes/progress_note.md", generated)
        self.assertIn("Conservatively summarised", generated)
        self.assertIn("Accepted evidence boundaries", generated)
        self.assertIn("aria-live=\"polite\"", generated)
        self.assertIn('class="evidence-statusline"', generated)
        self.assertIn("Source-grounded review", generated)
        self.assertIn("8 briefing items", generated)
        self.assertIn("1 source", generated)
        self.assertNotIn('<details class="evidence-sources" open>', generated)
        self.assertNotIn("source excerpt", generated.lower())

    def test_evidence_manifest_cannot_change_content_or_reference_unknown_records(self) -> None:
        cases: dict[str, tuple[Any, str]] = {}

        wrong_brief = self.valid_evidence()
        wrong_brief["brief_id"] = "0" * 64
        cases["brief ID"] = (wrong_brief, "brief_id")

        unknown_item = self.valid_evidence()
        unknown_item["items"]["key_findings-99"] = unknown_item["items"].pop(
            "key_findings-1"
        )
        cases["unknown item"] = (unknown_item, "item")

        unknown_source = self.valid_evidence()
        unknown_source["items"]["key_findings-1"]["references"][0][
            "source_id"
        ] = "source-999"
        cases["unknown source"] = (unknown_source, "source")

        content_override = self.valid_evidence()
        content_override["items"]["key_findings-1"]["text"] = "Replacement claim"
        cases["content override"] = (content_override, "unknown key")

        absolute_path = self.valid_evidence()
        absolute_path["sources"][0]["display_path"] = (
            "/" + "Users/synthetic-person/private.md"
        )
        cases["absolute path"] = (absolute_path, "relative")

        absolute_location = self.valid_evidence()
        absolute_location["items"]["recent_progress-1"]["references"][0][
            "location"
        ] = "/Volumes/SecretDrive/private/progress.md"
        cases["absolute evidence location"] = (absolute_location, "local path")

        local_modified_date = self.valid_evidence()
        local_modified_date["sources"][0]["modified_at"] = (
            "/Volumes/SyntheticDrive/private/progress.md"
        )
        cases["local path in modified date"] = (local_modified_date, "modified_at")

        unapproved_inference = self.valid_evidence()
        unapproved_inference["items"]["key_findings-1"][
            "wording_basis"
        ] = "inferred"
        unapproved_inference["items"]["key_findings-1"][
            "explicitly_approved"
        ] = False
        cases["unapproved inference"] = (unapproved_inference, "inferred")

        open_issue_in_approved_manifest = self.valid_evidence()
        open_issue_in_approved_manifest["issues"][0]["status"] = "open"
        cases["open issue in approved manifest"] = (
            open_issue_in_approved_manifest,
            "open",
        )

        for label, (evidence, expected_error) in cases.items():
            with self.subTest(label=label):
                self.assert_rejected_without_output_change(evidence=evidence)
                result, _ = self.run_builder(evidence=evidence)
                self.assertIn(expected_error, result.stderr.lower())

    def test_evidence_metadata_rejects_all_absolute_local_path_forms_atomically(self) -> None:
        cases: dict[str, dict[str, Any]] = {}

        posix_file_type = self.valid_evidence()
        posix_file_type["sources"][0]["file_type"] = "/mnt/private/format.txt"
        cases["POSIX path in source file type"] = posix_file_type

        posix_location = self.valid_evidence()
        posix_location["items"]["recent_progress-1"]["references"][0][
            "location"
        ] = "/srv/restricted/progress.md"
        cases["POSIX path in evidence location"] = posix_location

        posix_relevant_date = self.valid_evidence()
        posix_relevant_date["items"]["recent_progress-1"]["references"][0][
            "relevant_date"
        ] = "/data/private/dates.txt"
        cases["POSIX path in relevant date"] = posix_relevant_date

        windows_issue = self.valid_evidence()
        windows_issue["issues"][0]["description"] = (
            "Review C:\\Research\\private\\comments.docx before sharing."
        )
        cases["Windows path in issue description"] = windows_issue

        file_url_issue = self.valid_evidence()
        file_url_issue["issues"][0]["resolution"] = (
            "See " + "file://" + "/" + "Users/example/private/decision.txt"
        )
        cases["file URL in issue resolution"] = file_url_issue

        unc_issue = self.valid_evidence()
        unc_issue["issues"][0]["description"] = (
            r"Review \\server\share\private\comments.docx before sharing."
        )
        cases["UNC path in issue description"] = unc_issue

        home_relative_issue = self.valid_evidence()
        home_relative_issue["issues"][0]["resolution"] = (
            "See ~/Research/private/decision.txt"
        )
        cases["home-relative path in issue resolution"] = home_relative_issue

        named_home_issue = self.valid_evidence()
        named_home_issue["issues"][0]["resolution"] = (
            "See ~alice/private/decision.txt"
        )
        cases["named home path in issue resolution"] = named_home_issue

        standalone_named_home_issue = self.valid_evidence()
        standalone_named_home_issue["issues"][0]["resolution"] = (
            "The private working directory belongs to ~alice"
        )
        cases["standalone named home in issue resolution"] = (
            standalone_named_home_issue
        )

        colon_prefixed_posix = self.valid_evidence()
        colon_prefixed_posix["issues"][0]["description"] = (
            "Path:/mnt/private/results.csv"
        )
        cases["colon-prefixed POSIX path"] = colon_prefixed_posix

        posix_network_path = self.valid_evidence()
        posix_network_path["issues"][0]["resolution"] = (
            "See //private-server/research/results.csv"
        )
        cases["POSIX network path"] = posix_network_path

        for label, evidence in cases.items():
            with self.subTest(label=label):
                self.assert_rejected_without_output_change(evidence=evidence)
                result, _ = self.run_builder(evidence=evidence)
                self.assertIn("local path or file url", result.stderr.lower())

    def test_evidence_metadata_rejects_network_file_uris_atomically(self) -> None:
        for scheme in ("smb", "afp", "nfs", "sshfs", "sftp"):
            with self.subTest(scheme=scheme):
                evidence = self.valid_evidence()
                evidence["issues"][0]["resolution"] = (
                    f"See {scheme}://private-server/research/results.csv"
                )

                self.assert_rejected_without_output_change(evidence=evidence)
                result, _ = self.run_builder(evidence=evidence)
                self.assertIn("local path or file url", result.stderr.lower())

    def test_safe_metadata_path_detection_does_not_reject_public_or_relative_notation(self) -> None:
        evidence = self.valid_evidence()
        evidence["sources"][0]["file_type"] = "analysis/input"
        evidence["items"]["recent_progress-1"]["references"][0]["location"] = (
            "https://example.org/analysis/input"
        )
        evidence["issues"][0]["description"] = (
            "DOI: 10.1234/example.2026.001"
        )
        evidence["issues"][0]["resolution"] = "中文研究/方法"
        evidence["issues"][0]["resolution"] = (
            "中文研究/方法; an estimate of ~5 files was reviewed."
        )

        generated = self.build_html(evidence=evidence)

        for supplied in (
            "analysis/input",
            "https://example.org/analysis/input",
            "DOI: 10.1234/example.2026.001",
            "中文研究/方法; an estimate of ~5 files was reviewed.",
        ):
            self.assertIn(html.escape(supplied, quote=True), generated)

    def test_unconfirmed_manifest_rejects_confirmed_issue_statuses_atomically(self) -> None:
        for status in ("accepted", "resolved"):
            with self.subTest(status=status):
                evidence = self.valid_evidence()
                evidence["review_status"] = "automatic_unconfirmed"
                evidence["issues"][0]["status"] = status

                self.assert_rejected_without_output_change(evidence=evidence)
                result, _ = self.run_builder(evidence=evidence)
                self.assertIn("automatic_unconfirmed", result.stderr)
                self.assertIn("open", result.stderr)

    def test_resolved_issue_has_independent_metric_tag_heading_and_filter_semantics(self) -> None:
        evidence = self.valid_evidence()
        evidence["issues"][0]["status"] = "resolved"
        evidence["issues"][0]["resolution"] = (
            "The researcher confirmed the classification."
        )

        generated = self.build_html(evidence=evidence)

        self.assertIn("Resolved issues", generated)
        self.assertIn("Resolved evidence issues", generated)
        self.assertIn('<span class="uncertainty-tag">Resolved issue</span>', generated)
        self.assertIn(
            'id="evidence-item-unresolved_questions-1" tabindex="-1" '
            'data-evidence-record data-category="unresolved_questions"',
            generated,
        )
        record_start = generated.index(
            'id="evidence-item-unresolved_questions-1"'
        )
        record_end = generated.index("</article>", record_start)
        resolved_record = generated[record_start:record_end]
        self.assertIn('data-uncertain="false"', resolved_record)
        self.assertNotIn("Accepted boundary", generated)
        self.assertNotIn("Accepted boundaries", generated)
        self.assertNotIn("Accepted evidence boundaries", generated)

    def test_evidence_manifest_requires_complete_provenance_and_escapes_metadata(self) -> None:
        incomplete = self.valid_evidence()
        del incomplete["items"]["timeline-1"]
        self.assert_rejected_without_output_change(evidence=incomplete)

        malicious = self.valid_evidence()
        malicious["sources"][0]["display_path"] = "notes/<script>alert(1)</script>.md"
        malicious["items"]["recent_progress-1"]["references"][0][
            "location"
        ] = '<img src=x onerror="alert(1)">'
        malicious["issues"][0]["description"] = "<strong>Boundary</strong>"
        generated = self.build_html(evidence=malicious)

        self.assertNotIn("<script>alert(1)</script>", generated)
        self.assertNotIn("<img src=x", generated)
        self.assertNotIn("<strong>Boundary</strong>", generated)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", generated)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", generated)
        self.assertIn("&lt;strong&gt;Boundary&lt;/strong&gt;", generated)

    def test_cli_rejects_malformed_optional_arguments_without_touching_output(self) -> None:
        input_path = self.write_json("input.json", valid_payload())
        output_path = self.work / "briefing.html"
        output_path.write_text("existing output", encoding="utf-8")
        invalid_commands = (
            [sys.executable, str(BUILDER), str(input_path), str(output_path), "extra"],
            [
                sys.executable,
                str(BUILDER),
                str(input_path),
                str(output_path),
                "--config",
            ],
            [
                sys.executable,
                str(BUILDER),
                str(input_path),
                str(output_path),
                "--settings",
                str(input_path),
            ],
        )

        for command in invalid_commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    command,
                    cwd=SKILL_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage:", result.stderr)
                self.assertEqual(
                    output_path.read_text(encoding="utf-8"),
                    "existing output",
                )


if __name__ == "__main__":
    unittest.main()
