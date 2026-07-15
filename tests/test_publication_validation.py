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

PACKAGER_PATH = REPOSITORY_ROOT / "scripts" / "package_skill.py"
PACKAGER_SPECIFICATION = importlib.util.spec_from_file_location(
    "package_skill",
    PACKAGER_PATH,
)
if PACKAGER_SPECIFICATION is None or PACKAGER_SPECIFICATION.loader is None:
    raise RuntimeError("Could not load the Skill packager.")
PACKAGER = importlib.util.module_from_spec(PACKAGER_SPECIFICATION)
PACKAGER_SPECIFICATION.loader.exec_module(PACKAGER)


class PublicationValidationTests(unittest.TestCase):
    def runtime_issues(self, source: str) -> list[str]:
        inventory = VALIDATOR.PageInventory()
        inventory.feed(source)
        inventory.close()
        return VALIDATOR.runtime_dependency_issues(source, inventory)

    def write_archive(
        self,
        archive_path: Path,
        replacement: tuple[str, bytes] | None = None,
    ) -> None:
        expected = VALIDATOR.expected_archive_members()
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, source in expected.items():
                data = source.read_bytes()
                if replacement is not None and name.endswith(replacement[0]):
                    data = replacement[1]
                information = zipfile.ZipInfo(name, PACKAGER.ARCHIVE_TIMESTAMP)
                information.create_system = 3
                information.external_attr = 0o100644 << 16
                information.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(information, data)

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
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "stale.zip"
            self.write_archive(
                archive_path,
                replacement=("/SKILL.md", b"stale source"),
            )

            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "stale or modified member",
            ):
                VALIDATOR.validate_archive(archive_path)

    def test_archive_privacy_validation_scans_csv_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "private-csv.zip"
            private_email = "private.person" + "@" + "example.test"
            self.write_archive(
                archive_path,
                replacement=(
                    "/results_check.csv",
                    (
                        "source_id,owner\n"
                        f"source-001,{private_email}\n"
                    ).encode("utf-8"),
                ),
            )

            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "email address",
            ):
                VALIDATOR.validate_archive(archive_path)

    def test_archive_privacy_validation_rejects_generic_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "private-path.zip"
            self.write_archive(
                archive_path,
                replacement=(
                    "/results_check.csv",
                    b"source_id,location\nsource-001,Path:/mnt/private/results.csv\n",
                ),
            )

            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "absolute local path",
            ):
                VALIDATOR.validate_archive(archive_path)

    def test_privacy_validation_scans_csv_files(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="publication-csv-",
            dir=REPOSITORY_ROOT,
        ) as temporary_directory:
            fixture = Path(temporary_directory) / "mixed_sources.csv"
            private_email = "private.person" + "@" + "example.test"
            fixture.write_text(
                f"source_id,owner\nsource-001,{private_email}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "email address",
            ):
                VALIDATOR.validate_privacy([fixture])

    def test_privacy_validation_distinguishes_help_text_from_local_urls(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="publication-local-url-",
            dir=REPOSITORY_ROOT,
        ) as temporary_directory:
            fixture = Path(temporary_directory) / "offline_help.txt"
            fixture.write_text(
                "This output can be opened through file:// without a network.\n",
                encoding="utf-8",
            )
            VALIDATOR.validate_privacy([fixture])

            private_path = "/" + "Users/private-person/project/output.html"
            fixture.write_text(
                "Do not publish " + "file://" + private_path + ".\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "macOS user path|local file URL",
            ):
                VALIDATOR.validate_privacy([fixture])

    def test_privacy_validation_rejects_generic_absolute_paths_in_public_prose(self) -> None:
        fixtures = {
            "page.html": "<!doctype html><p>Private source: /mnt/private/results.csv</p>",
            "notes.md": "Private source: /srv/research/notes.md\n",
            "home.txt": "Private source: ~alice/research/results.csv\n",
            "standalone-home.txt": "Private working directory owner: ~alice\n",
            "network.txt": "Private source: smb://private-server/research/results.csv\n",
            "inventory.csv": (
                "source,location\n"
                "source-1,Path:/data/private/table.csv\n"
                "source-2,//private-server/research/table.csv\n"
            ),
        }
        with tempfile.TemporaryDirectory(
            prefix="publication-absolute-path-",
            dir=REPOSITORY_ROOT,
        ) as temporary_directory:
            for name, source in fixtures.items():
                path = Path(temporary_directory) / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(
                        VALIDATOR.PublicationError,
                        "absolute local path",
                    ):
                        VALIDATOR.validate_privacy([path])

    def test_privacy_validation_does_not_treat_markup_or_generic_code_as_private_paths(self) -> None:
        fixtures = {
            "page.html": (
                "<!doctype html><main><p>Share DOCX/PDF files, compare "
                "analysis/input labels and retain 研究/方法 terminology.</p></main>"
            ),
            "guide.md": "Run `#!/usr/bin/env python3` or visit https://example.test/guide.\n",
            "helper.py": "#!/usr/bin/env python3\n",
            "estimate.txt": "Approximately ~5 files were reviewed.\n",
        }
        with tempfile.TemporaryDirectory(
            prefix="publication-safe-slashes-",
            dir=REPOSITORY_ROOT,
        ) as temporary_directory:
            paths: list[Path] = []
            for name, source in fixtures.items():
                path = Path(temporary_directory) / name
                path.write_text(source, encoding="utf-8")
                paths.append(path)

            VALIDATOR.validate_privacy(paths)

    def test_privacy_validation_rejects_unsanctioned_folder_mode_output(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="publication-run-",
            dir=REPOSITORY_ROOT,
        ) as temporary_directory:
            fixture = Path(temporary_directory) / "briefing_draft.json"
            fixture.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "Folder Mode run artefact",
            ):
                VALIDATOR.validate_privacy([fixture])

    def test_privacy_validation_rejects_any_json_approval_record(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="publication-approval-",
            dir=REPOSITORY_ROOT,
        ) as temporary_directory:
            fixture = Path(temporary_directory) / "private_approval_record.json"
            fixture.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(
                VALIDATOR.PublicationError,
                "Folder Mode run artefact",
            ):
                VALIDATOR.validate_privacy([fixture])

    def test_packager_rejects_an_unlisted_canary_and_preserves_output(self) -> None:
        canary = PACKAGER.SKILL_ROOT / "unlisted-publication-canary.txt"
        self.addCleanup(canary.unlink, missing_ok=True)
        canary.write_text(
            "This file must never enter the public archive.\n",
            encoding="utf-8",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "skill.zip"
            original = b"existing archive bytes"
            output.write_bytes(original)

            with self.assertRaisesRegex(
                ValueError,
                "not listed in package_manifest.txt",
            ):
                PACKAGER.write_archive(output)

            self.assertEqual(output.read_bytes(), original)

    def test_packager_is_byte_for_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "first.zip"
            second = Path(temporary_directory) / "second.zip"

            first_count = PACKAGER.write_archive(first)
            second_count = PACKAGER.write_archive(second)

            self.assertGreater(first_count, 0)
            self.assertEqual(first_count, second_count)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_packager_refuses_to_write_inside_the_skill_source(self) -> None:
        output = PACKAGER.SKILL_ROOT / "would-overwrite-source.zip"
        self.addCleanup(output.unlink, missing_ok=True)

        with self.assertRaisesRegex(
            ValueError,
            "outside the Skill source folder",
        ):
            PACKAGER.write_archive(output)

        self.assertFalse(output.exists())

    def test_public_page_keeps_closing_sections_together_in_print(self) -> None:
        source = (REPOSITORY_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn(
            "figure, .resource-note, .workflow li, .takeaway, footer { break-inside: avoid; }",
            source,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
