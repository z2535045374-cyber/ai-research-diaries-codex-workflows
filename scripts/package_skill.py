#!/usr/bin/env python3
"""Build the standalone open-source Skill archive deterministically."""

from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "research-briefing-dashboard"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "Supervisor_Meeting_HTML_Skill.zip"
MANIFEST_PATH = SKILL_ROOT / "package_manifest.txt"
EXCLUDED_PARTS = {".pytest_cache", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
ARCHIVE_TIMESTAMP = (2026, 7, 14, 0, 0, 0)
FOLDER_MODE_ARTEFACT_NAMES = {
    "briefing_draft.json",
    "excluded_files.md",
    "final_briefing.html",
    "final_briefing_input.json",
    "final_source_map.md",
    "final_validation_report.md",
    "source_inventory.csv",
    "source_map.md",
    "unresolved_items.md",
}


def _is_excluded(relative: Path) -> bool:
    return (
        any(part in EXCLUDED_PARTS for part in relative.parts)
        or relative.suffix.lower() in EXCLUDED_SUFFIXES
    )


def _is_sanctioned_example(relative: PurePosixPath) -> bool:
    return relative.parts[:2] == ("examples", "folder-mode")


def _is_private_run_artefact(relative: PurePosixPath) -> bool:
    name = relative.name.lower()
    is_approval = relative.suffix.lower() == ".json" and "approval" in name
    if is_approval or ".research-briefing-work" in relative.parts:
        return True
    return (
        name in FOLDER_MODE_ARTEFACT_NAMES
        and not _is_sanctioned_example(relative)
    )


def manifest_members() -> list[PurePosixPath]:
    """Read and validate the explicit public package allow-list."""
    try:
        lines = MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Could not read {MANIFEST_PATH.name}: {exc}") from exc

    members: list[PurePosixPath] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        entry = raw_line.strip()
        if not entry or entry.startswith("#"):
            continue
        if "\\" in entry:
            raise ValueError(
                f"{MANIFEST_PATH.name}:{line_number}: use a POSIX relative path"
            )
        relative = PurePosixPath(entry)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError(
                f"{MANIFEST_PATH.name}:{line_number}: unsafe path {entry!r}"
            )
        normalised = relative.as_posix()
        if normalised != entry or normalised in seen:
            detail = "duplicate" if normalised in seen else "non-normalised"
            raise ValueError(
                f"{MANIFEST_PATH.name}:{line_number}: {detail} path {entry!r}"
            )
        if _is_private_run_artefact(relative):
            raise ValueError(
                f"{MANIFEST_PATH.name}:{line_number}: private Folder Mode run artefact {entry!r}"
            )
        seen.add(normalised)
        members.append(relative)

    if not members:
        raise ValueError(f"{MANIFEST_PATH.name} contains no package members.")
    if MANIFEST_PATH.name not in seen:
        raise ValueError(f"{MANIFEST_PATH.name} must list itself.")
    return sorted(members, key=PurePosixPath.as_posix)


def source_files() -> list[Path]:
    """Return only explicitly allow-listed Skill files in a stable order."""
    members = manifest_members()
    expected = {member.as_posix() for member in members}
    discovered: set[str] = set()
    for path in SKILL_ROOT.rglob("*"):
        relative = path.relative_to(SKILL_ROOT)
        if _is_excluded(relative):
            continue
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not supported: {relative}")
        if path.is_file():
            discovered.add(relative.as_posix())

    unlisted = sorted(discovered - expected)
    if unlisted:
        raise ValueError(
            "Skill source file(s) are not listed in package_manifest.txt: "
            + ", ".join(unlisted)
        )
    missing = sorted(expected - discovered)
    if missing:
        raise ValueError(
            "package_manifest.txt member(s) are missing: " + ", ".join(missing)
        )

    return [SKILL_ROOT.joinpath(*member.parts) for member in members]


def write_archive(output: Path) -> int:
    """Write the archive atomically and return its member count."""
    output = output.resolve()
    if output.is_relative_to(SKILL_ROOT.resolve()):
        raise ValueError("The archive output must be outside the Skill source folder.")
    files = source_files()
    if not files:
        raise ValueError("No Skill source files were found.")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for path in files:
                archive_name = path.relative_to(REPOSITORY_ROOT).as_posix()
                information = zipfile.ZipInfo(archive_name, ARCHIVE_TIMESTAMP)
                information.create_system = 3
                information.external_attr = 0o100644 << 16
                information.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(information, path.read_bytes())
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Archive path (default: Supervisor_Meeting_HTML_Skill.zip)",
    )
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    try:
        count = write_archive(output)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(f"Created {output} with {count} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
