#!/usr/bin/env python3
"""Regression tests for public HTML and Skill archive validation."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPOSITORY_ROOT / "scripts" / "validate_publication.py"
SPECIFICATION = importlib.util.spec_from_file_location(
    "validate_publication",
    VALIDATOR_PATH,
)
if SPECIFICATION is None or SPECIFICATION.loader is None:
    raise RuntimeError("Could not load the publication validator.")
VALIDATOR = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(VALIDATOR)


class PublicationValidationTests(unittest.TestCase):
    def runtime_issues(self, source: str) -> list[str]:
        inventory = VALIDATOR.PageInventory()
        inventory.feed(source)
        inventory.close()
        return VALIDATOR.runtime_dependency_issues(source, inventory)

    def test_protocol_relative_css_and_srcset_are_rejected(self) -> None:
        fixtures = {
            "CSS import": '<style>@import "//example.invalid/site.css";</style>',
            "CSS asset": '<style>body{background:url(//example.invalid/paper.png)}</style>',
            "srcset": '<img src="data:," srcset="image.png 1x, //example.invalid/image.png 2x" alt="">',
        }

        for label, source in fixtures.items():
            with self.subTest(label=label):
                self.assertTrue(self.runtime_issues(source))

    def test_archive_validation_rejects_stale_source_bytes(self) -> None:
        expected = VALIDATOR.expected_archive_members()
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "stale.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for name, source in expected.items():
                    data = source.read_bytes()
                    if name.endswith("/SKILL.md"):
                        data = b"stale source"
                    archive.writestr(name, data)

            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "stale or modified member",
            ):
                VALIDATOR.validate_archive(archive_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
