#!/usr/bin/env python3
"""Contract tests for source-grounded Folder Mode."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
FOLDER_MODE = SKILL_ROOT / "scripts" / "folder_mode.py"
BUILDER = SKILL_ROOT / "scripts" / "build_briefing.py"
FIXTURE_SOURCE = SKILL_ROOT / "examples" / "folder-mode" / "sources"
REVIEW_FILES = {
    "source_inventory.csv",
    "source_map.md",
    "briefing_draft.json",
    "unresolved_items.md",
    "excluded_files.md",
}
FINAL_FILES = {
    "final_briefing.html",
    "final_briefing_input.json",
    "final_source_map.md",
    "final_validation_report.md",
}
LIST_FIELDS = (
    "recent_progress",
    "completed_work",
    "key_findings",
    "unresolved_questions",
    "decisions_required",
    "next_actions",
    "timeline",
)


def provenance(
    source_id: str,
    source_file: str,
    location: str,
    relevant_date: str | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_file": source_file,
        "location": location,
        "relevant_date": relevant_date,
    }


def item(
    item_id: str,
    text: str,
    source_id: str,
    source_file: str,
    location: str,
    *,
    basis: str = "directly_stated",
    confidence: str = "high",
    review_status: str = "approved",
    inference_approved: bool = False,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "text": text,
        "confidence": confidence,
        "wording_basis": basis,
        "review_status": review_status,
        "inference_approved": inference_approved,
        "provenance": [
            provenance(source_id, source_file, location, "2026-07-14")
        ],
    }


def approved_draft(source_ids: dict[str, str]) -> dict[str, Any]:
    progress_id = source_ids["progress_note.md"]
    current_id = source_ids["manuscript_section_v2_current.md"]
    results_id = source_ids["results_check.csv"]
    comments_id = source_ids["supervisor_comments.txt"]
    return {
        "schema_version": 1,
        "mode": "research_folder",
        "context": {
            "source_label": "folder-mode/sources",
            "reporting_period": "1 June to 14 July 2026",
            "meeting_purpose": "Review recent document preparation",
            "attention_topics": ["Methods wording"],
        },
        "project_title": item(
            "project_title",
            "Synthetic document-screening study",
            current_id,
            "manuscript_section_v2_current.md",
            "heading: Methods section — current version",
            basis="conservatively_summarised",
        ),
        "recent_progress": [
            item(
                "recent_progress-1",
                "Completed the planned document-screening pass.",
                progress_id,
                "progress_note.md",
                "lines 5–5",
            )
        ],
        "completed_work": [
            item(
                "completed_work-1",
                "Revised the methods draft to distinguish automated checks from researcher review.",
                current_id,
                "manuscript_section_v2_current.md",
                "lines 3–3",
                basis="conservatively_summarised",
            )
        ],
        "key_findings": [
            item(
                "key_findings-1",
                "All selected files were accounted for in the synthetic quality check.",
                results_id,
                "results_check.csv",
                "row 2, columns status and review_note",
                basis="conservatively_summarised",
            )
        ],
        "unresolved_questions": [
            item(
                "unresolved_questions-1",
                "Should the comparison paragraph be classified as a finding or interpretation?",
                comments_id,
                "supervisor_comments.txt",
                "lines 3–3",
                basis="conservatively_summarised",
                confidence="medium",
            )
        ],
        "decisions_required": [
            item(
                "decisions_required-1",
                "Confirm the classification of the comparison paragraph.",
                comments_id,
                "supervisor_comments.txt",
                "lines 3–3",
                basis="inferred",
                confidence="medium",
                inference_approved=True,
            )
        ],
        "next_actions": [
            item(
                "next_actions-1",
                "Revise the comparison paragraph after the classification decision.",
                comments_id,
                "supervisor_comments.txt",
                "lines 3–3",
                basis="inferred",
                confidence="medium",
                inference_approved=True,
            )
        ],
        "timeline": [],
        "issues": [
            {
                "issue_id": "issue-1",
                "type": "classification_uncertainty",
                "description": "The comparison paragraph could be a finding or an interpretation.",
                "source_ids": [comments_id],
                "status": "accepted",
                "resolution": "Keep it as an unresolved question for supervisor discussion.",
            }
        ],
    }


class FolderModeTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.work = Path(self.temporary_directory.name)
        self.source = self.work / "sources"
        shutil.copytree(FIXTURE_SOURCE, self.source)
        self.review = self.work / "review"
        self.final = self.work / "final"

    def run_folder_mode(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(FOLDER_MODE), *arguments],
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def inventory(self, source: Path | None = None) -> subprocess.CompletedProcess[str]:
        result = self.run_folder_mode(
            "inventory",
            str(source or self.source),
            str(self.review),
            "--reporting-period",
            "1 June to 14 July 2026",
            "--meeting-purpose",
            "Review recent document preparation",
            "--attention-topic",
            "Methods wording",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def inventory_rows(self) -> list[dict[str, str]]:
        with (self.review / "source_inventory.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            return list(csv.DictReader(handle))

    def write_approved_draft(self) -> dict[str, Any]:
        rows = self.inventory_rows()
        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        cited_paths = {
            "progress_note.md",
            "manuscript_section_v2_current.md",
            "results_check.csv",
            "supervisor_comments.txt",
        }
        for row in rows:
            if row["relative_path"] in cited_paths:
                row["read_status"] = "read"
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        payload = approved_draft(source_ids)
        (self.review / "briefing_draft.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return payload

    def review_digest(self) -> str:
        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        digest = result.stdout.strip()
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        return digest

    def write_approval(
        self,
        digest: str,
        *,
        inferred: list[str] | None = None,
        acknowledged: list[str] | None = None,
    ) -> Path:
        approval = self.work / "approval.json"
        approval.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review_digest": digest,
                    "approve_finalisation": True,
                    "approved_inferred_item_ids": inferred or [],
                    "acknowledged_issue_ids": acknowledged or [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return approval

    def test_inventory_accounts_for_every_file_and_creates_only_review_files(self) -> None:
        self.inventory()

        self.assertEqual({path.name for path in self.review.iterdir()}, REVIEW_FILES)
        rows = self.inventory_rows()
        self.assertEqual(len(rows), len(list(self.source.rglob("*"))))
        self.assertEqual(len({row["source_id"] for row in rows}), len(rows))
        self.assertTrue(all(not Path(row["relative_path"]).is_absolute() for row in rows))
        dispositions = {row["relative_path"]: row["disposition"] for row in rows}
        self.assertEqual(dispositions["irrelevant_lunch_menu.txt"], "excluded")
        self.assertFalse(any((self.review / name).exists() for name in FINAL_FILES))

    def test_inventory_marks_current_previous_and_exact_duplicates_without_mtime_authority(self) -> None:
        shutil.copy2(
            self.source / "progress_note.md",
            self.source / "progress_note_copy.md",
        )
        self.inventory()
        rows = {row["relative_path"]: row for row in self.inventory_rows()}

        self.assertEqual(rows["manuscript_section_v1_previous.md"]["version_role"], "previous")
        self.assertEqual(rows["manuscript_section_v2_current.md"]["version_role"], "current_candidate")
        self.assertTrue(rows["progress_note.md"]["duplicate_group"])
        self.assertEqual(
            rows["progress_note.md"]["duplicate_group"],
            rows["progress_note_copy.md"]["duplicate_group"],
        )

    def test_zip_input_is_bounded_and_traversal_is_rejected_atomically(self) -> None:
        archive = self.work / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("safe/progress.md", "Approved synthetic progress")
            handle.writestr("../escape.txt", "must not escape")

        result = self.run_folder_mode("inventory", str(archive), str(self.review))

        self.assertEqual(result.returncode, 2)
        self.assertIn("unsafe", result.stderr.lower())
        self.assertFalse(self.review.exists())
        self.assertFalse((self.work / "escape.txt").exists())

    def test_zip_rejects_case_collisions_and_encrypted_members_atomically(self) -> None:
        collision = self.work / "collision.zip"
        with zipfile.ZipFile(collision, "w") as handle:
            handle.writestr("notes/Progress.md", "First synthetic note")
            handle.writestr("notes/progress.md", "Second synthetic note")

        collision_result = self.run_folder_mode(
            "inventory", str(collision), str(self.review)
        )

        self.assertEqual(collision_result.returncode, 2)
        self.assertIn("colliding", collision_result.stderr.lower())
        self.assertFalse(self.review.exists())

        encrypted = self.work / "encrypted.zip"
        with zipfile.ZipFile(encrypted, "w") as handle:
            handle.writestr("notes/progress.md", "Synthetic note")
        archive_bytes = bytearray(encrypted.read_bytes())
        local_header = archive_bytes.index(b"PK\x03\x04")
        central_header = archive_bytes.index(b"PK\x01\x02")
        archive_bytes[local_header + 6 : local_header + 8] = (
            int.from_bytes(archive_bytes[local_header + 6 : local_header + 8], "little")
            | 0x1
        ).to_bytes(2, "little")
        archive_bytes[central_header + 8 : central_header + 10] = (
            int.from_bytes(
                archive_bytes[central_header + 8 : central_header + 10], "little"
            )
            | 0x1
        ).to_bytes(2, "little")
        encrypted.write_bytes(archive_bytes)

        encrypted_result = self.run_folder_mode(
            "inventory", str(encrypted), str(self.review)
        )

        self.assertEqual(encrypted_result.returncode, 2)
        self.assertIn("encrypted", encrypted_result.stderr.lower())
        self.assertFalse(self.review.exists())

    def test_zip_directory_exclusion_is_recursive_without_a_directory_member(self) -> None:
        archive = self.work / "excluded-directory.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("public/progress.md", "Synthetic public progress")
            handle.writestr("private_notes/secret.md", "Synthetic excluded note")

        result = self.run_folder_mode(
            "inventory",
            str(archive),
            str(self.review),
            "--reporting-period",
            "1 June to 14 July 2026",
            "--exclude",
            "private_notes",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {row["relative_path"]: row for row in self.inventory_rows()}
        self.assertEqual(rows["public/progress.md"]["disposition"], "included")
        self.assertRegex(rows["public/progress.md"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(rows["private_notes/secret.md"]["disposition"], "excluded")
        self.assertIn("Explicit user exclusion", rows["private_notes/secret.md"]["reason"])
        self.assertEqual(rows["private_notes/secret.md"]["sha256"], "")

    def test_zip_default_generated_and_irrelevant_directories_are_excluded_recursively(self) -> None:
        archive = self.work / "default-excluded-directories.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("public/progress.md", "Synthetic public progress")
            handle.writestr("generated/secret.md", "Synthetic generated output")
            handle.writestr("irrelevant_notes/lunch.md", "Synthetic irrelevant note")

        result = self.run_folder_mode(
            "inventory",
            str(archive),
            str(self.review),
            "--reporting-period",
            "1 June to 14 July 2026",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {row["relative_path"]: row for row in self.inventory_rows()}
        self.assertEqual(rows["public/progress.md"]["disposition"], "included")
        self.assertRegex(rows["public/progress.md"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(rows["generated/secret.md"]["disposition"], "excluded")
        self.assertIn("Generated output", rows["generated/secret.md"]["reason"])
        self.assertEqual(rows["generated/secret.md"]["sha256"], "")
        self.assertEqual(rows["irrelevant_notes/lunch.md"]["disposition"], "excluded")
        self.assertIn("irrelevant", rows["irrelevant_notes/lunch.md"]["reason"].lower())
        self.assertEqual(rows["irrelevant_notes/lunch.md"]["sha256"], "")

    def test_zip_rejects_noncanonical_path_aliases_atomically(self) -> None:
        for index, alias in enumerate(("notes/./item.md", "notes//item.md"), start=1):
            with self.subTest(alias=alias):
                archive = self.work / f"alias-{index}.zip"
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("notes/item.md", "Canonical synthetic note")
                    handle.writestr(alias, "Aliased synthetic note")

                review = self.work / f"review-{index}"
                result = self.run_folder_mode("inventory", str(archive), str(review))

                self.assertEqual(result.returncode, 2)
                self.assertIn("non-canonical", result.stderr.lower())
                self.assertFalse(review.exists())

    def test_explicit_directory_exclusion_survives_review_revalidation(self) -> None:
        excluded_directory = self.source / "private_working_notes"
        excluded_directory.mkdir()
        (excluded_directory / "capture.bin").write_bytes(
            b"synthetic excluded unsupported capture"
        )
        result = self.run_folder_mode(
            "inventory",
            str(self.source),
            str(self.review),
            "--reporting-period",
            "1 June to 14 July 2026",
            "--exclude",
            "private_working_notes",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = self.inventory_rows()
        mechanical_issues = json.loads(
            (self.review / "briefing_draft.json").read_text(encoding="utf-8")
        )["issues"]
        excluded = {
            row["relative_path"]: row
            for row in rows
            if row["disposition"] == "excluded"
        }
        self.assertIn("private_working_notes", excluded)
        self.assertIn("private_working_notes/capture.bin", excluded)
        self.assertIn(
            "Explicit user exclusion",
            excluded["private_working_notes/capture.bin"]["reason"],
        )
        self.assertEqual(excluded["private_working_notes/capture.bin"]["sha256"], "")
        self.assertTrue(
            any(issue["type"] == "unsupported_file" for issue in mechanical_issues)
        )

        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        cited_paths = {
            "progress_note.md",
            "manuscript_section_v2_current.md",
            "results_check.csv",
            "supervisor_comments.txt",
        }
        for row in rows:
            if row["relative_path"] in cited_paths:
                row["read_status"] = "read"
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        draft = approved_draft(source_ids)
        draft["issues"] = mechanical_issues
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )

        validation_without_exclusion = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )
        self.assertEqual(validation_without_exclusion.returncode, 2)
        self.assertIn("changed", validation_without_exclusion.stderr.lower())

        validation = self.run_folder_mode(
            "validate-review",
            str(self.source),
            str(self.review),
            "--exclude",
            "private_working_notes",
        )

        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertRegex(validation.stdout.strip(), r"^[0-9a-f]{64}$")

        for issue in draft["issues"]:
            issue["status"] = "accepted"
            issue["resolution"] = "Retain the exclusion and review the risk privately."
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        digest_result = self.run_folder_mode(
            "validate-review",
            str(self.source),
            str(self.review),
            "--exclude",
            "private_working_notes",
        )
        self.assertEqual(digest_result.returncode, 0, digest_result.stderr)
        approval = self.write_approval(
            digest_result.stdout.strip(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=[issue["issue_id"] for issue in draft["issues"]],
        )

        finalisation = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
            "--exclude",
            "private_working_notes",
        )

        self.assertEqual(finalisation.returncode, 0, finalisation.stderr)
        self.assertEqual({path.name for path in self.final.iterdir()}, FINAL_FILES)

    def test_included_file_cannot_be_forged_as_an_explicit_exclusion(self) -> None:
        self.inventory()
        rows = self.inventory_rows()
        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        cited_paths = {
            "progress_note.md",
            "manuscript_section_v2_current.md",
            "results_check.csv",
            "supervisor_comments.txt",
        }
        forged_name = "analysis_checks.py"
        for row in rows:
            if row["relative_path"] in cited_paths:
                row["read_status"] = "read"
            if row["relative_path"] == forged_name:
                row.update(
                    disposition="excluded",
                    reader_requirement="None",
                    read_status="not_read",
                    reason=f"Explicit user exclusion: {forged_name}",
                )
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        (self.review / "briefing_draft.json").write_text(
            json.dumps(approved_draft(source_ids), indent=2), encoding="utf-8"
        )

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("disposition changed", result.stderr.lower())

    def test_unsupported_file_is_reported_and_cannot_support_an_item(self) -> None:
        unsupported = self.source / "instrument_capture.bin"
        unsupported.write_bytes(b"synthetic binary fixture")
        self.inventory()
        rows = self.inventory_rows()
        unsupported_row = next(
            row for row in rows if row["relative_path"] == unsupported.name
        )
        self.assertEqual(unsupported_row["disposition"], "unsupported")
        unresolved = (self.review / "unresolved_items.md").read_text(encoding="utf-8")
        self.assertIn(unsupported.name, unresolved)
        draft = self.write_approved_draft()
        draft["recent_progress"][0]["provenance"] = [
            provenance(
                unsupported_row["source_id"],
                unsupported.name,
                "binary record",
            )
        ]
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported source", result.stderr.lower())

    def test_validate_review_requires_provenance_and_reports_uncertainty(self) -> None:
        self.inventory()
        payload = self.write_approved_draft()
        payload["recent_progress"][0]["provenance"] = []
        (self.review / "briefing_draft.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        result = self.run_folder_mode("validate-review", str(self.source), str(self.review))

        self.assertEqual(result.returncode, 2)
        self.assertIn("provenance", result.stderr.lower())

    def test_mechanical_confidentiality_issue_cannot_be_deleted(self) -> None:
        confidential = self.source / "participant_notes.md"
        confidential.write_text("Synthetic participant note.", encoding="utf-8")
        self.inventory()
        rows = self.inventory_rows()
        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        for row in rows:
            if row["relative_path"] in {
                "progress_note.md",
                "manuscript_section_v2_current.md",
                "results_check.csv",
                "supervisor_comments.txt",
                confidential.name,
            }:
                row["read_status"] = "read"
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        draft = approved_draft(source_ids)
        draft["issues"] = []
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        (self.review / "unresolved_items.md").write_text(
            "# Unresolved items\n\nNo issues remain.\n", encoding="utf-8"
        )

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("mechanical", result.stderr.lower())
        self.assertIn("possible_confidentiality", result.stderr)

    def test_unsupported_issue_cannot_be_hidden_by_forging_an_explicit_exclusion(self) -> None:
        unsupported = self.source / "capture.bin"
        unsupported.write_bytes(b"synthetic unsupported capture")
        self.inventory()
        rows = self.inventory_rows()
        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        cited_paths = {
            "progress_note.md",
            "manuscript_section_v2_current.md",
            "results_check.csv",
            "supervisor_comments.txt",
        }
        for row in rows:
            if row["relative_path"] in cited_paths:
                row["read_status"] = "read"
            if row["relative_path"] == unsupported.name:
                row.update(
                    disposition="excluded",
                    reader_requirement="None",
                    read_status="not_read",
                    reason=f"Explicit user exclusion: {unsupported.name}",
                )
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        draft = approved_draft(source_ids)
        draft["issues"] = []
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        (self.review / "unresolved_items.md").write_text(
            "# Unresolved items\n\nNo issues remain.\n", encoding="utf-8"
        )

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("disposition changed", result.stderr.lower())
        self.assertIn(unsupported.name, result.stderr)

    def test_absolute_provenance_location_is_rejected(self) -> None:
        self.inventory()
        draft = self.write_approved_draft()
        draft["recent_progress"][0]["provenance"][0]["location"] = (
            "/Volumes/SecretDrive/private/progress_note.md"
        )
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("absolute", result.stderr.lower())

    def test_arbitrary_absolute_paths_are_rejected_across_draft_metadata(self) -> None:
        self.inventory()
        baseline = self.write_approved_draft()
        mutations = {
            "POSIX provenance": lambda draft: draft["recent_progress"][0]["provenance"][0].update(
                location="/mnt/private/project/progress_note.md"
            ),
            "POSIX item text": lambda draft: draft["recent_progress"][0].update(
                text="Review /srv/private/project/progress_note.md before the meeting."
            ),
            "POSIX issue description": lambda draft: draft["issues"][0].update(
                description="The conflicting value is in /data/private/results.csv."
            ),
            "colon-delimited POSIX path": lambda draft: draft["issues"][0].update(
                description="Path:/mnt/private/results.csv"
            ),
            "forward-slash UNC path": lambda draft: draft["issues"][0].update(
                description="//private-server/research/results.csv"
            ),
            "file URL resolution": lambda draft: draft["issues"][0].update(
                resolution="Use " + "file://" + "/" + "Users/example/private/results.csv."
            ),
            "Windows context": lambda draft: draft["context"].update(
                meeting_purpose=r"Review C:\Private\project\notes.docx"
            ),
            "Windows UNC context": lambda draft: draft["context"].update(
                meeting_purpose=r"Review \\private-server\research\notes.docx"
            ),
            "home-relative context": lambda draft: draft["context"].update(
                meeting_purpose="Review ~/private/project/notes.md"
            ),
            "named home context": lambda draft: draft["context"].update(
                meeting_purpose="Review ~alice/private/project/notes.md"
            ),
            "standalone named home context": lambda draft: draft["context"].update(
                meeting_purpose="The private working directory belongs to ~alice"
            ),
            "SMB URI context": lambda draft: draft["context"].update(
                meeting_purpose="Review smb://private-server/share/notes.md"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                draft = json.loads(json.dumps(baseline))
                mutate(draft)
                (self.review / "briefing_draft.json").write_text(
                    json.dumps(draft, indent=2), encoding="utf-8"
                )

                result = self.run_folder_mode(
                    "validate-review", str(self.source), str(self.review)
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("absolute", result.stderr.lower())

    def test_inventory_free_text_metadata_rejects_an_arbitrary_absolute_path(self) -> None:
        self.inventory()
        self.write_approved_draft()
        rows = self.inventory_rows()
        original_requirement = rows[0]["reader_requirement"]
        rows[0]["reader_requirement"] = "/mnt/private/custom-reader"
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("absolute", result.stderr.lower())

        rows[0]["reader_requirement"] = original_requirement
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        with (self.review / "source_map.md").open("a", encoding="utf-8") as handle:
            handle.write("\nInternal reader: /srv/private/source-map.md\n")

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("absolute", result.stderr.lower())

    def test_relative_urls_and_prose_slashes_are_not_treated_as_absolute_paths(self) -> None:
        self.inventory()
        draft = self.write_approved_draft()
        draft["recent_progress"][0]["text"] = (
            "Compared analysis/input labels, 研究/方法 terminology and "
            "https://example.invalid/reference; an estimate of ~5 files was "
            "discussed without exposing a local path."
        )
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generic_build_directory_does_not_block_ordinary_build_prose(self) -> None:
        build_directory = self.source / "build"
        build_directory.mkdir()
        (build_directory / "restricted_research_roster.csv").write_text(
            "synthetic,excluded\n", encoding="utf-8"
        )
        self.inventory()
        rows = {row["relative_path"]: row for row in self.inventory_rows()}
        self.assertEqual(rows["build"]["disposition"], "excluded")
        self.assertEqual(
            rows["build/restricted_research_roster.csv"]["disposition"],
            "excluded",
        )
        self.assertEqual(rows["build/restricted_research_roster.csv"]["sha256"], "")
        draft = self.write_approved_draft()
        draft["recent_progress"][0]["text"] = "Completed the model build."
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        approval = self.write_approval(
            self.review_digest(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=["issue-1"],
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "Completed the model build.",
            (self.final / "final_briefing.html").read_text(encoding="utf-8"),
        )

    def test_default_excluded_directory_descendant_filename_cannot_leak(self) -> None:
        build_directory = self.source / "build"
        build_directory.mkdir()
        excluded_name = "restricted_research_roster.csv"
        (build_directory / excluded_name).write_text(
            "synthetic,excluded\n", encoding="utf-8"
        )
        self.inventory()
        draft = self.write_approved_draft()
        draft["recent_progress"][0]["text"] = (
            f"Reviewed {excluded_name} during the model build."
        )
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        approval = self.write_approval(
            self.review_digest(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=["issue-1"],
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("uncited or unshareable source", result.stderr.lower())
        self.assertFalse(self.final.exists())

    def test_inventory_modified_date_cannot_be_replaced_with_a_local_path(self) -> None:
        self.inventory()
        self.write_approved_draft()
        rows = self.inventory_rows()
        rows[0]["modified_at"] = "/Volumes/SyntheticDrive/private/source.md"
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        result = self.run_folder_mode(
            "validate-review", str(self.source), str(self.review)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("modified_at", result.stderr)

    def test_provenance_requires_an_explicit_read_status(self) -> None:
        self.inventory()
        rows = self.inventory_rows()
        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        (self.review / "briefing_draft.json").write_text(
            json.dumps(approved_draft(source_ids), indent=2), encoding="utf-8"
        )

        result = self.run_folder_mode("validate-review", str(self.source), str(self.review))

        self.assertEqual(result.returncode, 2)
        self.assertIn("read_status is read", result.stderr)

    def test_finalisation_is_blocked_without_approval_and_is_atomic(self) -> None:
        self.inventory()
        self.write_approved_draft()

        result = self.run_folder_mode(
            "finalise", str(self.source), str(self.review), str(self.final)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("approval", result.stderr.lower())
        self.assertFalse(self.final.exists())

    def test_digest_change_invalidates_approval(self) -> None:
        self.inventory()
        payload = self.write_approved_draft()
        digest = self.review_digest()
        approval = self.write_approval(
            digest,
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=["issue-1"],
        )
        payload["recent_progress"][0]["text"] += " Changed after approval."
        (self.review / "briefing_draft.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("digest", result.stderr.lower())
        self.assertFalse(self.final.exists())

    def test_source_change_after_review_invalidates_approval(self) -> None:
        self.inventory()
        self.write_approved_draft()
        approval = self.write_approval(
            self.review_digest(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=["issue-1"],
        )
        (self.source / "progress_note.md").write_text(
            "# Changed after review\n\nThis invalidates the recorded source hash.\n",
            encoding="utf-8",
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("source", result.stderr.lower())
        self.assertFalse(self.final.exists())

    def test_inferred_items_require_explicit_approval(self) -> None:
        self.inventory()
        self.write_approved_draft()
        approval = self.write_approval(self.review_digest(), acknowledged=["issue-1"])

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("inferred", result.stderr.lower())
        self.assertFalse(self.final.exists())

    def test_approved_finalisation_uses_stable_schema_and_adds_evidence_explorer(self) -> None:
        self.inventory()
        draft = self.write_approved_draft()
        approval = self.write_approval(
            self.review_digest(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=["issue-1"],
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({path.name for path in self.final.iterdir()}, FINAL_FILES)
        final_input = json.loads(
            (self.final / "final_briefing_input.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(final_input), {"project_title", *LIST_FIELDS})
        self.assertEqual(final_input["project_title"], draft["project_title"]["text"])
        html_source = (self.final / "final_briefing.html").read_text(encoding="utf-8")
        self.assertIn("Evidence Explorer", html_source)
        self.assertIn('id="group-evidence"', html_source)
        self.assertIn("Filter evidence", html_source)
        self.assertIn("View evidence", html_source)
        self.assertNotIn(str(self.work), html_source)
        for field in LIST_FIELDS:
            for draft_item in draft[field]:
                self.assertIn(draft_item["text"], html_source)
        report = (self.final / "final_validation_report.md").read_text(encoding="utf-8")
        self.assertIn("PASS", report)
        self.assertIn("Evidence Explorer", report)

    def test_explicit_unconfirmed_generation_warns_and_rejects_inference(self) -> None:
        self.inventory()
        draft = self.write_approved_draft()
        result_with_inference = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--allow-unconfirmed",
        )
        self.assertEqual(result_with_inference.returncode, 2)
        self.assertIn("inferred", result_with_inference.stderr.lower())
        self.assertFalse(self.final.exists())

        for field in ("decisions_required", "next_actions"):
            draft[field] = []
        draft["issues"][0]["status"] = "open"
        draft["issues"][0]["resolution"] = None
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--allow-unconfirmed",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        html_source = (self.final / "final_briefing.html").read_text(encoding="utf-8")
        source_map = (self.final / "final_source_map.md").read_text(encoding="utf-8")
        report = (self.final / "final_validation_report.md").read_text(encoding="utf-8")
        self.assertIn("Unconfirmed draft", html_source)
        self.assertIn("without researcher confirmation", html_source)
        self.assertIn("Briefing items", html_source)
        self.assertIn("Sources used by this unconfirmed draft", html_source)
        self.assertIn("Evidence boundaries requiring review", html_source)
        self.assertIn("Open:", html_source)
        self.assertNotIn("Approved briefing items", html_source)
        self.assertNotIn("Approved sources used by this briefing", html_source)
        self.assertNotIn("Accepted evidence boundaries", html_source)
        self.assertIn("unconfirmed draft content", source_map)
        self.assertNotIn("approved relative source locations", source_map)
        self.assertIn("unconfirmed-review bypass", report)
        self.assertNotIn("Approved item reconciliation", report)

    def test_unconfirmed_generation_neutralises_unapproved_final_issue_states(self) -> None:
        self.inventory()
        baseline = self.write_approved_draft()
        for field in ("decisions_required", "next_actions"):
            baseline[field] = []
        for status in ("accepted", "resolved"):
            with self.subTest(status=status):
                draft = json.loads(json.dumps(baseline))
                draft["issues"][0].update(
                    status=status,
                    resolution=f"Claimed as {status} without researcher confirmation.",
                )
                (self.review / "briefing_draft.json").write_text(
                    json.dumps(draft, indent=2), encoding="utf-8"
                )
                final_directory = self.work / f"final-{status}"

                result = self.run_folder_mode(
                    "finalise",
                    str(self.source),
                    str(self.review),
                    str(final_directory),
                    "--allow-unconfirmed",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                html_source = (final_directory / "final_briefing.html").read_text(
                    encoding="utf-8"
                )
                source_map = (final_directory / "final_source_map.md").read_text(
                    encoding="utf-8"
                )
                self.assertNotIn("Accepted evidence boundaries", html_source)
                self.assertNotIn("Accepted boundary", html_source)
                self.assertNotIn("Resolved evidence issues", html_source)
                self.assertNotIn(f"({status})", source_map)
                self.assertNotIn(f"Claimed as {status}", source_map)
                self.assertIn("Evidence boundaries requiring review", source_map)
                self.assertIn("Not researcher-confirmed", source_map)
                self.assertIn("(open)", source_map)

    def test_mixed_source_issue_does_not_expose_an_excluded_source(self) -> None:
        self.inventory()
        draft = self.write_approved_draft()
        rows = self.inventory_rows()
        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        excluded_name = "irrelevant_lunch_menu.txt"
        draft["issues"].append(
            {
                "issue_id": "issue-2",
                "type": "other",
                "description": f"Compare supervisor comments with {excluded_name}.",
                "source_ids": [
                    source_ids["supervisor_comments.txt"],
                    source_ids[excluded_name],
                ],
                "status": "accepted",
                "resolution": f"Do not expose {excluded_name} in the public briefing.",
            }
        )
        draft["issues"].append(
            {
                "issue_id": "issue-3",
                "type": "other",
                "description": f"The undeclared source is {excluded_name}.",
                "source_ids": [source_ids["supervisor_comments.txt"]],
                "status": "accepted",
                "resolution": f"Exclude {excluded_name} from the shareable briefing.",
            }
        )
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        approval = self.write_approval(
            self.review_digest(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=["issue-1", "issue-2", "issue-3"],
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        html_source = (self.final / "final_briefing.html").read_text(encoding="utf-8")
        source_map = (self.final / "final_source_map.md").read_text(encoding="utf-8")
        self.assertNotIn(excluded_name, html_source)
        self.assertNotIn(excluded_name, source_map)

    def test_final_items_cannot_mention_an_uncited_inventory_filename(self) -> None:
        self.inventory()
        baseline = self.write_approved_draft()
        excluded_name = "irrelevant_lunch_menu.txt"
        mutations = {
            "item text": lambda draft: draft["recent_progress"][0].update(
                text=f"Compared the progress note with {excluded_name}."
            ),
            "provenance location": lambda draft: draft["recent_progress"][0]["provenance"][0].update(
                location=f"cross-reference to {excluded_name}"
            ),
            "source cited only by another item": lambda draft: draft["recent_progress"][0].update(
                text="Cross-checked results_check.csv during the progress review."
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                draft = json.loads(json.dumps(baseline))
                mutate(draft)
                (self.review / "briefing_draft.json").write_text(
                    json.dumps(draft, indent=2), encoding="utf-8"
                )
                approval = self.write_approval(
                    self.review_digest(),
                    inferred=["decisions_required-1", "next_actions-1"],
                    acknowledged=["issue-1"],
                )
                final_directory = self.work / f"final-{label.replace(' ', '-')}"

                result = self.run_folder_mode(
                    "finalise",
                    str(self.source),
                    str(self.review),
                    str(final_directory),
                    "--approval",
                    str(approval),
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("uncited or unshareable source", result.stderr.lower())
                self.assertFalse(final_directory.exists())

    def test_final_items_cannot_expose_an_explicitly_excluded_directory(self) -> None:
        excluded_directory_name = "private_working_notes"
        excluded_directory = self.source / excluded_directory_name
        excluded_directory.mkdir()
        (excluded_directory / "capture.bin").write_bytes(b"synthetic private capture")
        result = self.run_folder_mode(
            "inventory",
            str(self.source),
            str(self.review),
            "--reporting-period",
            "1 June to 14 July 2026",
            "--exclude",
            excluded_directory_name,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = self.inventory_rows()
        source_ids = {row["relative_path"]: row["source_id"] for row in rows}
        for row in rows:
            if row["relative_path"] in {
                "progress_note.md",
                "manuscript_section_v2_current.md",
                "results_check.csv",
                "supervisor_comments.txt",
            }:
                row["read_status"] = "read"
        with (self.review / "source_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        draft = approved_draft(source_ids)
        mechanical_issues = json.loads(
            (self.review / "briefing_draft.json").read_text(encoding="utf-8")
        )["issues"]
        for issue in mechanical_issues:
            issue["status"] = "accepted"
            issue["resolution"] = "Retain the exclusion and review the risk privately."
        draft["issues"] = mechanical_issues
        draft["recent_progress"][0]["text"] += (
            f" Materials in {excluded_directory_name} were also considered."
        )
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        digest_result = self.run_folder_mode(
            "validate-review",
            str(self.source),
            str(self.review),
            "--exclude",
            excluded_directory_name,
        )
        self.assertEqual(digest_result.returncode, 0, digest_result.stderr)
        approval = self.write_approval(
            digest_result.stdout.strip(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=[issue["issue_id"] for issue in draft["issues"]],
        )

        finalisation = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
            "--exclude",
            excluded_directory_name,
        )

        self.assertEqual(finalisation.returncode, 2)
        self.assertIn("uncited or unshareable source", finalisation.stderr.lower())
        self.assertFalse(self.final.exists())

    def test_resolved_issues_have_a_distinct_final_source_map_heading(self) -> None:
        self.inventory()
        draft = self.write_approved_draft()
        draft["issues"][0].update(
            status="resolved",
            resolution="The paragraph remains an interpretation.",
        )
        (self.review / "briefing_draft.json").write_text(
            json.dumps(draft, indent=2), encoding="utf-8"
        )
        approval = self.write_approval(
            self.review_digest(),
            inferred=["decisions_required-1", "next_actions-1"],
        )

        result = self.run_folder_mode(
            "finalise",
            str(self.source),
            str(self.review),
            str(self.final),
            "--approval",
            str(approval),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        source_map = (self.final / "final_source_map.md").read_text(encoding="utf-8")
        self.assertIn("## Resolved evidence issues", source_map)
        self.assertIn("(resolved)", source_map)
        self.assertNotIn("Accepted evidence boundaries", source_map)

    def test_legacy_builder_commands_remain_available(self) -> None:
        payload = {
            "project_title": "Legacy example",
            **{field: [] for field in LIST_FIELDS},
        }
        source = self.work / "input.json"
        output = self.work / "legacy.html"
        source.write_text(json.dumps(payload), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(BUILDER), str(source), str(output)],
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Evidence Explorer", output.read_text(encoding="utf-8"))

    def test_relative_paths_work_when_invoked_from_the_repository_root(self) -> None:
        repository_root = SKILL_ROOT.parent
        script = FOLDER_MODE.relative_to(repository_root)
        source = os.path.relpath(self.source, repository_root)
        review = os.path.relpath(self.review, repository_root)
        final = os.path.relpath(self.final, repository_root)

        inventory = subprocess.run(
            [
                sys.executable,
                str(script),
                "inventory",
                source,
                review,
                "--reporting-period",
                "1 June to 14 July 2026",
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(inventory.returncode, 0, inventory.stderr)
        self.write_approved_draft()
        digest_result = subprocess.run(
            [sys.executable, str(script), "validate-review", source, review],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(digest_result.returncode, 0, digest_result.stderr)
        approval = self.write_approval(
            digest_result.stdout.strip(),
            inferred=["decisions_required-1", "next_actions-1"],
            acknowledged=["issue-1"],
        )
        approval_relative = os.path.relpath(approval, repository_root)

        generated = subprocess.run(
            [
                sys.executable,
                str(script),
                "finalise",
                source,
                review,
                final,
                "--approval",
                approval_relative,
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.assertEqual({path.name for path in self.final.iterdir()}, FINAL_FILES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
