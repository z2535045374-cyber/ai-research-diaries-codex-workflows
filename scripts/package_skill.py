#!/usr/bin/env python3
"""Build the standalone open-source Skill archive deterministically."""

from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "research-briefing-dashboard"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "Supervisor_Meeting_HTML_Skill.zip"
EXCLUDED_PARTS = {".DS_Store", ".pytest_cache", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
ARCHIVE_TIMESTAMP = (2026, 7, 14, 0, 0, 0)


def source_files() -> list[Path]:
    """Return the publishable Skill files in a stable order."""
    files: list[Path] = []
    for path in SKILL_ROOT.rglob("*"):
        relative = path.relative_to(SKILL_ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not supported: {relative}")
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda path: path.as_posix())


def write_archive(output: Path) -> int:
    """Write the archive atomically and return its member count."""
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
