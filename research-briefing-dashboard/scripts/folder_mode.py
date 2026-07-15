#!/usr/bin/env python3
"""Prepare and finalise source-grounded Folder Mode briefings.

The script deliberately performs no semantic summarisation.  It inventories a
folder or ZIP, validates an agent-prepared provenance-bearing draft, binds a
researcher approval to the review artefacts and invokes the stable HTML builder.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import html
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


SKILL_ROOT = Path(__file__).resolve().parents[1]
BUILDER = SKILL_ROOT / "scripts" / "build_briefing.py"

REVIEW_FILE_NAMES = (
    "source_inventory.csv",
    "source_map.md",
    "briefing_draft.json",
    "unresolved_items.md",
    "excluded_files.md",
)
FINAL_FILE_NAMES = (
    "final_briefing.html",
    "final_briefing_input.json",
    "final_source_map.md",
    "final_validation_report.md",
)
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
    "project_title": "Project title",
    "recent_progress": "Recent progress",
    "completed_work": "Completed work",
    "key_findings": "Key findings",
    "unresolved_questions": "Unresolved questions",
    "decisions_required": "Decisions required",
    "next_actions": "Next actions",
    "timeline": "Timeline",
}

INVENTORY_COLUMNS = (
    "source_id",
    "relative_path",
    "detected_type",
    "size_bytes",
    "modified_at",
    "sha256",
    "disposition",
    "reader_requirement",
    "read_status",
    "duplicate_group",
    "version_group",
    "version_role",
    "version_ambiguous",
    "confidentiality_flag",
    "reason",
)

TEXT_TYPES = {
    ".bib": "BibTeX",
    ".c": "C source",
    ".cc": "C++ source",
    ".cpp": "C++ source",
    ".csv": "CSV",
    ".css": "CSS source",
    ".do": "Stata script",
    ".h": "C header",
    ".hpp": "C++ header",
    ".htm": "HTML",
    ".html": "HTML",
    ".ipynb": "Jupyter notebook JSON",
    ".ini": "INI configuration",
    ".java": "Java source",
    ".jl": "Julia source",
    ".js": "JavaScript source",
    ".json": "JSON",
    ".jsx": "JSX source",
    ".kt": "Kotlin source",
    ".log": "Plain-text log",
    ".lua": "Lua source",
    ".m": "MATLAB source",
    ".markdown": "Markdown",
    ".md": "Markdown",
    ".mjs": "JavaScript module",
    ".pl": "Perl source",
    ".py": "Python source",
    ".qmd": "Quarto Markdown",
    ".r": "R source",
    ".rb": "Ruby source",
    ".rmd": "R Markdown",
    ".rs": "Rust source",
    ".sas": "SAS script",
    ".sh": "Shell script",
    ".sps": "SPSS syntax",
    ".sql": "SQL",
    ".swift": "Swift source",
    ".tex": "LaTeX",
    ".toml": "TOML",
    ".ts": "TypeScript source",
    ".tsx": "TSX source",
    ".txt": "Plain text",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".zsh": "Z shell script",
}
DOCUMENT_TYPES = {
    ".docx": "Word document",
    ".pdf": "PDF",
    ".pptx": "PowerPoint presentation",
    ".xlsx": "Excel workbook",
}
ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "bower_components",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "site-packages",
    "target",
    "venv",
}
GENERATED_FILE_NAMES = {
    *REVIEW_FILE_NAMES,
    *FINAL_FILE_NAMES,
    "supervisor_briefing_dashboard.html",
    "meeting_brief.html",
}
CONFIDENTIAL_NAME_TERMS = {
    "confidential",
    "consent",
    "identifiable",
    "participant",
    "private",
    "sensitive",
}

CONFIDENCE_VALUES = {"high", "medium", "low"}
WORDING_BASIS_VALUES = {
    "directly_stated",
    "conservatively_summarised",
    "inferred",
}
REVIEW_STATUS_VALUES = {"pending", "approved", "removed"}
ISSUE_STATUS_VALUES = {"open", "accepted", "resolved"}
ISSUE_TYPE_VALUES = {
    "classification_uncertainty",
    "competing_versions",
    "confidentiality_risk",
    "duplicate_version",
    "interpretation_uncertainty",
    "missing_reporting_period",
    "numerical_conflict",
    "other",
    "possible_confidentiality",
    "unclear_date",
    "unclear_owner",
    "unreadable_source",
    "unsupported_file",
}

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_ZIP_MEMBERS = 10_000
MAX_ZIP_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ZIP_RATIO = 200
MAX_ITEM_CODE_POINTS = 20_000
MAX_LOCATION_CODE_POINTS = 2_000
MAX_ISSUE_CODE_POINTS = 10_000
REVIEW_DIGEST_DOMAIN = b"research-briefing-folder-review-v1\0"
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
WINDOWS_PATH_IN_TEXT_PATTERN = re.compile(r"(?<!\w)[A-Za-z]:[\\/]")
WINDOWS_UNC_IN_TEXT_PATTERN = re.compile(
    r'(?<![\w\\])\\{2}[^\\\s]+\\[^\\\s]+'
)
POSIX_ABSOLUTE_IN_TEXT_PATTERN = re.compile(
    r'(?<![\w._/-])/(?![/\s])[^<>\s"\']+'
)
FORWARD_SLASH_UNC_IN_TEXT_PATTERN = re.compile(
    r"(?<![:/])//[^/\s]+/[^/\s]+"
)
HOME_PATH_IN_TEXT_PATTERN = re.compile(
    r"(?<![\w._:/-])~(?:"
    r"[A-Za-z][A-Za-z0-9._-]*(?=$|[\s,;:)\]}])"
    r"|(?:[A-Za-z0-9._-]+)?[\\/]"
    r")"
)
FILESYSTEM_URI_IN_TEXT_PATTERN = re.compile(
    r"(?<![\w+.-])(?:file|smb|afp|nfs|sshfs|sftp)://",
    re.IGNORECASE,
)
ISO_DATE_OR_DATETIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?)?\Z"
)
VERSION_TOKEN_PATTERN = re.compile(r"^v(?:ersion)?(\d+(?:\.\d+)*)$", re.IGNORECASE)


class FolderModeError(ValueError):
    """An invalid or unsafe Folder Mode input."""


def _json_object_without_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FolderModeError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise FolderModeError(f"Invalid JSON constant: {value}")


def load_json(path: Path, description: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FolderModeError(f"Could not read {description}: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except FolderModeError:
        raise
    except json.JSONDecodeError as exc:
        raise FolderModeError(
            f"Invalid JSON in {description} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def atomic_text_write(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise FolderModeError(f"Could not write {path.name}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def normalise_relative_path(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace(os.sep, "/"))


def source_identifier(relative_path: str) -> str:
    digest = hashlib.sha256(normalise_relative_path(relative_path).encode("utf-8")).hexdigest()
    return f"source-{digest[:16]}"


def utc_modified_at(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise FolderModeError(f"Could not hash source file {path.name}: {exc}") from exc
    return digest.hexdigest()


def _is_absolute_or_unsafe_path(value: str) -> bool:
    if not value or CONTROL_CHARACTER_PATTERN.search(value):
        return True
    if value.startswith(("/", "\\", "~", "file://")):
        return True
    if WINDOWS_ABSOLUTE_PATTERN.match(value):
        return True
    pure = PurePosixPath(value.replace("\\", "/"))
    return pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts)


def _contains_absolute_path(value: str) -> bool:
    lowered = value.casefold()
    if (
        "file://" in lowered
        or FILESYSTEM_URI_IN_TEXT_PATTERN.search(value)
        or WINDOWS_PATH_IN_TEXT_PATTERN.search(value)
        or WINDOWS_UNC_IN_TEXT_PATTERN.search(value)
        or POSIX_ABSOLUTE_IN_TEXT_PATTERN.search(value)
        or FORWARD_SLASH_UNC_IN_TEXT_PATTERN.search(value)
        or HOME_PATH_IN_TEXT_PATTERN.search(value)
        or value.strip() == "/"
    ):
        return True
    return False


def _validate_iso_date_or_datetime(value: str, label: str) -> None:
    if not ISO_DATE_OR_DATETIME_PATTERN.fullmatch(value):
        raise FolderModeError(f"{label} must be an ISO 8601 date or date-time")
    normalised = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise FolderModeError(f"{label} must be a valid ISO 8601 date or date-time") from exc


def _require_plain_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FolderModeError(f"{label} must be non-empty text")
    if len(value) > maximum:
        raise FolderModeError(f"{label} exceeds {maximum} characters")
    if CONTROL_CHARACTER_PATTERN.search(value):
        raise FolderModeError(f"{label} contains a control character")
    if _contains_absolute_path(value):
        raise FolderModeError(f"{label} must not contain an absolute or file URL path")
    return value


def detect_type(relative_path: str, *, directory: bool = False, symlink: bool = False) -> str:
    if symlink:
        return "Symbolic link"
    if directory:
        return "Directory"
    suffix = PurePosixPath(relative_path).suffix.casefold()
    if suffix in TEXT_TYPES:
        return TEXT_TYPES[suffix]
    if suffix in DOCUMENT_TYPES:
        return DOCUMENT_TYPES[suffix]
    if suffix in ARCHIVE_SUFFIXES:
        return "Archive"
    return "Unsupported"


def exclusion_reason(
    relative_path: str,
    *,
    is_directory: bool,
    user_patterns: Sequence[str],
) -> str | None:
    pure = PurePosixPath(relative_path)
    name = pure.name
    folded_name = name.casefold()
    parts = [part.casefold() for part in pure.parts]
    for pattern in user_patterns:
        for length in range(1, len(pure.parts) + 1):
            candidate = PurePosixPath(*pure.parts[:length])
            if fnmatch.fnmatch(candidate.as_posix(), pattern) or fnmatch.fnmatch(
                candidate.name, pattern
            ):
                return f"Explicit user exclusion: {pattern}"
    if name.startswith(".") or any(part.startswith(".") for part in pure.parts):
        return "Hidden system item"
    if name.startswith("~$"):
        return "Temporary Office file"
    if any(part in EXCLUDED_DIRECTORY_NAMES for part in parts):
        return "Dependency, cache or generated-output directory"
    if folded_name in {name.casefold() for name in GENERATED_FILE_NAMES}:
        return "Previously generated briefing artefact"
    directory_parts = parts if is_directory else parts[:-1]
    if any(
        part in {"generated", "briefing_output", "briefing_outputs"}
        for part in directory_parts
    ):
        return "Generated output directory"
    if folded_name.startswith(("irrelevant_", "irrelevant-")) or any(
        part.startswith(("irrelevant_", "irrelevant-")) for part in directory_parts
    ):
        return "Explicitly labelled as irrelevant source material"
    return None


def _blank_inventory_row(relative_path: str) -> dict[str, str]:
    return {column: "" for column in INVENTORY_COLUMNS} | {
        "source_id": source_identifier(relative_path),
        "relative_path": relative_path,
        "version_ambiguous": "false",
        "confidentiality_flag": "false",
    }


def _confidentiality_flag(relative_path: str) -> bool:
    tokens = set(re.split(r"[^a-z0-9]+", relative_path.casefold()))
    return bool(tokens & CONFIDENTIAL_NAME_TERMS)


def _inventory_regular_file(
    path: Path,
    relative_path: str,
    *,
    user_patterns: Sequence[str],
    forced_exclusion_reason: str | None = None,
) -> dict[str, str]:
    try:
        details = path.stat(follow_symlinks=False)
    except OSError as exc:
        row = _blank_inventory_row(relative_path)
        row.update(
            detected_type=detect_type(relative_path),
            disposition="unreadable",
            reader_requirement="Manual inspection required",
            read_status="unreadable",
            reason=f"Could not inspect file metadata: {exc}",
        )
        return row

    row = _blank_inventory_row(relative_path)
    kind = detect_type(relative_path)
    reason = forced_exclusion_reason or exclusion_reason(
        relative_path, is_directory=False, user_patterns=user_patterns
    )
    row.update(
        detected_type=kind,
        size_bytes=str(details.st_size),
        modified_at=utc_modified_at(details.st_mtime),
        confidentiality_flag=str(_confidentiality_flag(relative_path)).lower(),
    )
    if forced_exclusion_reason is None and details.st_size <= MAX_FILE_BYTES:
        row["sha256"] = sha256_file(path)
    elif forced_exclusion_reason is None:
        row["reason"] = f"File exceeds the {MAX_FILE_BYTES}-byte inventory hashing limit"

    if reason:
        row.update(
            disposition="excluded",
            reader_requirement="None",
            read_status="not_read",
            reason=reason,
        )
    elif details.st_size > MAX_FILE_BYTES:
        row.update(
            disposition="unreadable",
            reader_requirement="Manual size review required",
            read_status="unreadable",
        )
    elif kind in TEXT_TYPES.values():
        row.update(
            disposition="included",
            reader_requirement="Coding-agent text reader",
            read_status="awaiting_agent_review",
            reason="Directly readable text; semantic review is still required",
        )
    elif kind in DOCUMENT_TYPES.values():
        row.update(
            disposition="included",
            reader_requirement=f"Coding-agent {kind} reader",
            read_status="awaiting_agent_review",
            reason="Requires an available document-reading tool",
        )
    else:
        row.update(
            disposition="unsupported",
            reader_requirement="No supported reader identified",
            read_status="unreadable",
            reason="Unsupported file type; it must not be silently ignored",
        )
    return row


def inventory_folder(source: Path, user_patterns: Sequence[str]) -> list[dict[str, str]]:
    if not source.is_dir():
        raise FolderModeError("Folder Mode source must be a directory or a ZIP archive")
    rows: list[dict[str, str]] = []

    def visit(
        directory: Path,
        relative_directory: PurePosixPath | None = None,
        inherited_exclusion: str | None = None,
    ) -> None:
        try:
            entries = sorted(
                os.scandir(directory),
                key=lambda entry: unicodedata.normalize("NFC", entry.name).casefold(),
            )
        except OSError as exc:
            raise FolderModeError(f"Could not inventory directory {directory.name}: {exc}") from exc

        for entry in entries:
            relative = PurePosixPath(entry.name) if relative_directory is None else relative_directory / entry.name
            relative_path = normalise_relative_path(relative.as_posix())
            try:
                is_symlink = entry.is_symlink()
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError as exc:
                row = _blank_inventory_row(relative_path)
                row.update(
                    detected_type="Unreadable",
                    disposition="unreadable",
                    reader_requirement="Manual inspection required",
                    read_status="unreadable",
                    reason=f"Could not inspect directory entry: {exc}",
                )
                rows.append(row)
                continue

            if is_symlink:
                row = _blank_inventory_row(relative_path)
                try:
                    link_target = os.readlink(entry.path)
                    row["sha256"] = hashlib.sha256(link_target.encode("utf-8", "surrogateescape")).hexdigest()
                    link_stat = entry.stat(follow_symlinks=False)
                    row["size_bytes"] = str(link_stat.st_size)
                    row["modified_at"] = utc_modified_at(link_stat.st_mtime)
                except OSError:
                    pass
                row.update(
                    detected_type=detect_type(relative_path, symlink=True),
                    disposition="excluded",
                    reader_requirement="None",
                    read_status="not_read",
                    reason=(
                        inherited_exclusion + "; symbolic link listed but not followed"
                        if inherited_exclusion
                        else "Symbolic link listed but not followed"
                    ),
                )
                rows.append(row)
                continue

            if is_directory:
                row = _blank_inventory_row(relative_path)
                reason = inherited_exclusion or exclusion_reason(
                    relative_path,
                    is_directory=True,
                    user_patterns=user_patterns,
                )
                try:
                    details = entry.stat(follow_symlinks=False)
                    row["modified_at"] = utc_modified_at(details.st_mtime)
                except OSError:
                    pass
                if reason:
                    row.update(
                        detected_type=detect_type(relative_path, directory=True),
                        disposition="excluded",
                        reader_requirement="None",
                        read_status="not_read",
                        reason=reason + "; the directory is excluded recursively",
                    )
                    rows.append(row)
                    # Record excluded descendants without reading their content.
                    # Their paths and basenames are needed to prevent later draft
                    # text from exposing files hidden inside a default excluded
                    # directory such as ``build`` or ``node_modules``.
                    visit(Path(entry.path), relative, reason)
                else:
                    row.update(
                        detected_type=detect_type(relative_path, directory=True),
                        disposition="container",
                        reader_requirement="None",
                        read_status="not_applicable",
                        reason="Directory container; child entries inventoried",
                    )
                    rows.append(row)
                    visit(Path(entry.path), relative)
                continue

            rows.append(
                _inventory_regular_file(
                    Path(entry.path),
                    relative_path,
                    user_patterns=user_patterns,
                    forced_exclusion_reason=inherited_exclusion,
                )
            )
    visit(source)
    return rows


def _safe_zip_member_name(name: str) -> str:
    if "\\" in name:
        raise FolderModeError(f"Unsafe ZIP member path uses backslashes: {name!r}")
    normalised = normalise_relative_path(name.rstrip("/"))
    if _is_absolute_or_unsafe_path(normalised):
        raise FolderModeError(f"Unsafe ZIP member path: {name!r}")
    canonical = PurePosixPath(normalised).as_posix()
    if canonical != normalised:
        raise FolderModeError(f"Unsafe ZIP member path is non-canonical: {name!r}")
    return canonical


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def inventory_zip(source: Path, user_patterns: Sequence[str]) -> list[dict[str, str]]:
    if not source.is_file() or source.suffix.casefold() != ".zip":
        raise FolderModeError("Folder Mode source must be a directory or a ZIP archive")
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise FolderModeError(f"Could not open ZIP archive safely: {exc}") from exc

    with archive:
        members = archive.infolist()
        if len(members) > MAX_ZIP_MEMBERS:
            raise FolderModeError(f"Unsafe ZIP has more than {MAX_ZIP_MEMBERS} members")
        total_size = sum(info.file_size for info in members)
        if total_size > MAX_ZIP_TOTAL_BYTES:
            raise FolderModeError("Unsafe ZIP expands beyond the permitted total size")

        seen: set[str] = set()
        prepared: list[tuple[zipfile.ZipInfo, str]] = []
        for info in members:
            relative_path = _safe_zip_member_name(info.filename)
            collision_key = unicodedata.normalize("NFC", relative_path).casefold()
            if collision_key in seen:
                raise FolderModeError(f"Unsafe ZIP contains a duplicate or colliding member: {relative_path}")
            seen.add(collision_key)
            if info.flag_bits & 0x1:
                raise FolderModeError(f"Unsafe ZIP contains an encrypted member: {relative_path}")
            if _zip_member_is_symlink(info):
                raise FolderModeError(f"Unsafe ZIP contains a symbolic link: {relative_path}")
            if not info.is_dir() and PurePosixPath(relative_path).suffix.casefold() in ARCHIVE_SUFFIXES:
                raise FolderModeError(f"Unsafe ZIP contains a nested archive: {relative_path}")
            if info.file_size > MAX_FILE_BYTES:
                raise FolderModeError(f"Unsafe ZIP member exceeds the permitted size: {relative_path}")
            if (
                info.file_size > 1024 * 1024
                and info.compress_size > 0
                and info.file_size / info.compress_size > MAX_ZIP_RATIO
            ):
                raise FolderModeError(f"Unsafe ZIP member has a suspicious compression ratio: {relative_path}")
            prepared.append((info, relative_path))

        rows: list[dict[str, str]] = []
        for info, relative_path in prepared:
            is_directory = info.is_dir()
            row = _blank_inventory_row(relative_path)
            reason = exclusion_reason(
                relative_path,
                is_directory=is_directory,
                user_patterns=user_patterns,
            )
            row.update(
                detected_type=detect_type(relative_path, directory=is_directory),
                size_bytes=str(info.file_size),
                modified_at="-".join(f"{value:02d}" for value in info.date_time[:3])
                + "T"
                + ":".join(f"{value:02d}" for value in info.date_time[3:]),
                confidentiality_flag=str(_confidentiality_flag(relative_path)).lower(),
            )
            if is_directory:
                row.update(
                    disposition="excluded" if reason else "container",
                    reader_requirement="None",
                    read_status="not_read" if reason else "not_applicable",
                    reason=reason or "Directory container; member entries inventoried",
                )
                rows.append(row)
                continue
            if reason:
                # Excluded ZIP members are inventoried from central-directory
                # metadata only. Do not open, read or hash their content.
                row.update(
                    disposition="excluded",
                    reader_requirement="None",
                    read_status="not_read",
                    reason=reason,
                )
                rows.append(row)
                continue
            try:
                with archive.open(info, "r") as handle:
                    digest = hashlib.sha256()
                    consumed = 0
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        consumed += len(block)
                        if consumed > MAX_FILE_BYTES:
                            raise FolderModeError(f"Unsafe ZIP member exceeds its declared bound: {relative_path}")
                        digest.update(block)
                    if consumed != info.file_size:
                        raise FolderModeError(f"Unsafe ZIP member size changed while reading: {relative_path}")
                    row["sha256"] = digest.hexdigest()
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise FolderModeError(f"Could not read ZIP member {relative_path}: {exc}") from exc

            kind = row["detected_type"]
            if kind in TEXT_TYPES.values():
                row.update(
                    disposition="included",
                    reader_requirement="Coding-agent text reader",
                    read_status="awaiting_agent_review",
                    reason="Directly readable text; semantic review is still required",
                )
            elif kind in DOCUMENT_TYPES.values():
                row.update(
                    disposition="included",
                    reader_requirement=f"Coding-agent {kind} reader",
                    read_status="awaiting_agent_review",
                    reason="Requires an available document-reading tool",
                )
            else:
                row.update(
                    disposition="unsupported",
                    reader_requirement="No supported reader identified",
                    read_status="unreadable",
                    reason="Unsupported file type; it must not be silently ignored",
                )
            rows.append(row)
        return rows


def _version_signature(relative_path: str) -> tuple[str, tuple[int, ...] | None, str | None]:
    pure = PurePosixPath(relative_path)
    tokens = [token for token in re.split(r"[_ .-]+", pure.stem.casefold()) if token]
    version: tuple[int, ...] | None = None
    role: str | None = None
    retained = list(tokens)
    while retained:
        token = retained[-1]
        match = VERSION_TOKEN_PATTERN.match(token)
        if match:
            version = tuple(int(part) for part in match.group(1).split("."))
            retained.pop()
            continue
        if token in {"previous", "prior", "old", "superseded"}:
            role = "previous"
            retained.pop()
            continue
        if token in {"current", "latest", "final"}:
            role = "current"
            retained.pop()
            continue
        if token in {"draft", "copy"} and (version is not None or role is not None):
            retained.pop()
            continue
        break
    base = "_".join(retained) or pure.stem.casefold()
    key = f"{pure.parent.as_posix().casefold()}|{base}|{pure.suffix.casefold()}"
    return key, version, role


def apply_duplicate_and_version_signals(rows: list[dict[str, str]]) -> None:
    digest_groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row["sha256"]:
            digest_groups.setdefault(row["sha256"], []).append(row)
    for digest, group in digest_groups.items():
        if len(group) > 1:
            duplicate_group = f"duplicate-{digest[:12]}"
            for row in group:
                row["duplicate_group"] = duplicate_group

    version_groups: dict[str, list[tuple[dict[str, str], tuple[int, ...] | None, str | None]]] = {}
    for row in rows:
        if row["disposition"] not in {"included", "unsupported", "unreadable"}:
            continue
        key, version, role = _version_signature(row["relative_path"])
        if version is not None or role is not None:
            version_groups.setdefault(key, []).append((row, version, role))
    for key, group in version_groups.items():
        if len(group) < 2:
            continue
        version_group = f"version-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}"
        for row, _, _ in group:
            row["version_group"] = version_group
        explicit_current = [(row, version) for row, version, role in group if role == "current"]
        if len(explicit_current) == 1:
            explicit_current[0][0]["version_role"] = "current_candidate"
            for row, version, role in group:
                if row is explicit_current[0][0]:
                    continue
                if role == "previous" or version is not None:
                    row["version_role"] = "previous"
            continue
        if len(explicit_current) > 1:
            for row, _ in explicit_current:
                row["version_role"] = "competing_current_candidate"
                row["version_ambiguous"] = "true"
            for row, _, role in group:
                if role == "previous":
                    row["version_role"] = "previous"
            continue

        numbered = [(row, version) for row, version, _ in group if version is not None]
        if numbered:
            highest = max(version for _, version in numbered if version is not None)
            highest_rows = [row for row, version in numbered if version == highest]
            if len(highest_rows) == 1:
                highest_rows[0]["version_role"] = "current_candidate"
                for row, _ in numbered:
                    if row is not highest_rows[0]:
                        row["version_role"] = "previous"
            else:
                for row in highest_rows:
                    row["version_role"] = "competing_current_candidate"
                    row["version_ambiguous"] = "true"
        for row, _, role in group:
            if role == "previous":
                row["version_role"] = "previous"


def inventory_source(source: Path, user_patterns: Sequence[str] = ()) -> list[dict[str, str]]:
    if not source.exists():
        raise FolderModeError(f"Source does not exist: {source}")
    rows = inventory_folder(source, user_patterns) if source.is_dir() else inventory_zip(source, user_patterns)
    apply_duplicate_and_version_signals(rows)
    rows.sort(key=lambda row: (row["relative_path"].casefold(), row["relative_path"]))
    identifiers = [row["source_id"] for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise FolderModeError("Source identifiers collided after path normalisation")
    return rows


def inventory_csv_text(rows: Sequence[dict[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=INVENTORY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def initial_issues(rows: Sequence[dict[str, str]], reporting_period: str | None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def append_issue(issue_type: str, description: str, source_ids: Sequence[str]) -> None:
        issues.append(
            {
                "issue_id": f"issue-{len(issues) + 1}",
                "type": issue_type,
                "description": description,
                "source_ids": list(source_ids),
                "status": "open",
                "resolution": None,
            }
        )

    if not reporting_period:
        append_issue(
            "missing_reporting_period",
            "No reporting period was supplied. Confirm the intended time boundary before classification.",
            [],
        )
    ambiguous = [row for row in rows if row["version_ambiguous"] == "true"]
    for version_group in sorted({row["version_group"] for row in ambiguous if row["version_group"]}):
        members = [row for row in ambiguous if row["version_group"] == version_group]
        append_issue(
            "competing_versions",
            "Several files carry competing current-version signals: "
            + ", ".join(row["relative_path"] for row in members),
            [row["source_id"] for row in members],
        )
    for row in rows:
        if row["disposition"] in {"unsupported", "unreadable"}:
            append_issue(
                "unsupported_file" if row["disposition"] == "unsupported" else "unreadable_source",
                f"The source could not be read automatically: {row['relative_path']}",
                [row["source_id"]],
            )
        if row["confidentiality_flag"] == "true":
            append_issue(
                "possible_confidentiality",
                f"The filename suggests a possible confidentiality risk: {row['relative_path']}",
                [row["source_id"]],
            )
    return issues


def source_map_scaffold() -> str:
    sections = "\n\n".join(
        f"## {FIELD_LABELS[field]}\n\nNo source-grounded items have been proposed yet."
        for field in ("project_title", *LIST_FIELDS)
    )
    return (
        "# Source map\n\n"
        "This map is a review artefact. The coding agent must replace each empty section "
        "with proposed briefing items and relative source locations before seeking approval.\n\n"
        + sections
        + "\n"
    )


def unresolved_markdown(rows: Sequence[dict[str, str]], issues: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Unresolved items",
        "",
        "These items require researcher or coding-agent attention before finalisation.",
        "",
    ]
    if issues:
        for issue in issues:
            lines.append(f"- **{issue['issue_id']} — {issue['type']}**: {issue['description']}")
    else:
        lines.append("- No mechanical inventory issue was detected. Semantic conflicts may still emerge during reading.")
    reader_files = [
        row for row in rows
        if row["disposition"] == "included" and row["detected_type"] in DOCUMENT_TYPES.values()
    ]
    if reader_files:
        lines.extend(("", "## Files requiring a document reader", ""))
        lines.extend(
            f"- `{row['relative_path']}` — {row['reader_requirement']}"
            for row in reader_files
        )
    lines.append("")
    return "\n".join(lines)


def excluded_markdown(rows: Sequence[dict[str, str]]) -> str:
    excluded = [row for row in rows if row["disposition"] == "excluded"]
    lines = [
        "# Excluded files",
        "",
        "Excluded material remains visible here and is not used to draft briefing content.",
        "",
    ]
    if excluded:
        lines.extend(f"- `{row['relative_path']}` — {row['reason']}" for row in excluded)
    else:
        lines.append("- No files were excluded.")
    lines.append("")
    return "\n".join(lines)


def draft_scaffold(
    source: Path,
    rows: Sequence[dict[str, str]],
    *,
    reporting_period: str | None,
    meeting_purpose: str | None,
    attention_topics: Sequence[str],
    mechanical_rows: Sequence[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "research_folder",
        "context": {
            "source_label": source.name,
            "reporting_period": reporting_period,
            "meeting_purpose": meeting_purpose,
            "attention_topics": list(attention_topics),
        },
        "project_title": None,
        **{field: [] for field in LIST_FIELDS},
        "issues": initial_issues(mechanical_rows or rows, reporting_period),
    }


def _ensure_output_is_outside_source(source: Path, output: Path) -> None:
    if not source.is_dir():
        return
    source_resolved = source.resolve()
    output_resolved = output.resolve(strict=False)
    try:
        output_resolved.relative_to(source_resolved)
    except ValueError:
        return
    raise FolderModeError("Review and final output directories must be outside the source folder")


def create_inventory(
    source: Path,
    review_directory: Path,
    *,
    reporting_period: str | None,
    meeting_purpose: str | None,
    attention_topics: Sequence[str],
    excludes: Sequence[str],
) -> None:
    _ensure_output_is_outside_source(source, review_directory)
    if review_directory.exists():
        raise FolderModeError("Review directory already exists; remove it or choose a new path")
    rows = inventory_source(source, excludes)
    mechanical_rows = rows if not excludes else inventory_source(source, ())
    review_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{review_directory.name}.", dir=review_directory.parent))
    try:
        issues = initial_issues(mechanical_rows, reporting_period)
        (staging / "source_inventory.csv").write_text(
            inventory_csv_text(rows), encoding="utf-8", newline="\n"
        )
        (staging / "source_map.md").write_text(source_map_scaffold(), encoding="utf-8")
        (staging / "briefing_draft.json").write_text(
            json.dumps(
                draft_scaffold(
                    source,
                    rows,
                    reporting_period=reporting_period,
                    meeting_purpose=meeting_purpose,
                    attention_topics=attention_topics,
                    mechanical_rows=mechanical_rows,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (staging / "unresolved_items.md").write_text(
            unresolved_markdown(rows, issues), encoding="utf-8"
        )
        (staging / "excluded_files.md").write_text(
            excluded_markdown(rows), encoding="utf-8"
        )
        if {path.name for path in staging.iterdir()} != set(REVIEW_FILE_NAMES):
            raise FolderModeError("Internal error: review staging set is incomplete")
        os.replace(staging, review_directory)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def load_inventory(review_directory: Path) -> list[dict[str, str]]:
    path = review_directory / "source_inventory.csv"
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != INVENTORY_COLUMNS:
                raise FolderModeError("source_inventory.csv has an invalid or reordered header")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise FolderModeError(f"Could not read source_inventory.csv: {exc}") from exc
    paths: set[str] = set()
    identifiers: set[str] = set()
    for index, row in enumerate(rows, start=2):
        relative_path = row["relative_path"]
        if _is_absolute_or_unsafe_path(relative_path):
            raise FolderModeError(f"source_inventory.csv row {index} has an unsafe relative path")
        for field, maximum in (
            ("reader_requirement", 2_000),
            ("duplicate_group", 200),
            ("version_group", 200),
            ("reason", 10_000),
        ):
            if row[field]:
                _require_plain_text(
                    row[field],
                    f"source_inventory.csv row {index} {field}",
                    maximum=maximum,
                )
        expected_identifier = source_identifier(relative_path)
        if row["source_id"] != expected_identifier:
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid source_id")
        if relative_path in paths or row["source_id"] in identifiers:
            raise FolderModeError("source_inventory.csv contains a duplicate path or source_id")
        paths.add(relative_path)
        identifiers.add(row["source_id"])
        if row["sha256"] and not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid SHA-256")
        if row["detected_type"] not in {
            *TEXT_TYPES.values(),
            *DOCUMENT_TYPES.values(),
            "Archive",
            "Directory",
            "Symbolic link",
            "Unsupported",
            "Unreadable",
        }:
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid detected_type")
        if row["size_bytes"] and not row["size_bytes"].isdigit():
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid size_bytes value")
        if row["modified_at"]:
            _validate_iso_date_or_datetime(
                row["modified_at"],
                f"source_inventory.csv row {index} modified_at",
            )
        if row["disposition"] not in {
            "container",
            "excluded",
            "included",
            "unreadable",
            "unsupported",
        }:
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid disposition")
        if row["read_status"] not in {
            "awaiting_agent_review",
            "not_applicable",
            "not_read",
            "partially_read",
            "read",
            "unreadable",
        }:
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid read_status")
        if row["version_role"] not in {
            "",
            "competing_current_candidate",
            "current_candidate",
            "previous",
        }:
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid version_role")
        if row["version_ambiguous"] not in {"true", "false"}:
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid version_ambiguous value")
        if row["confidentiality_flag"] not in {"true", "false"}:
            raise FolderModeError(f"source_inventory.csv row {index} has an invalid confidentiality_flag")
    return rows


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    supplied = set(value)
    missing = sorted(expected - supplied)
    unknown = sorted(supplied - expected)
    issues: list[str] = []
    if missing:
        issues.append("missing " + ", ".join(missing))
    if unknown:
        issues.append("unknown " + ", ".join(unknown))
    if issues:
        raise FolderModeError(f"{label} has invalid keys ({'; '.join(issues)})")


def _validate_provenance(
    value: Any,
    label: str,
    inventory_by_id: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise FolderModeError(f"{label}.provenance must contain at least one source record")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for index, record in enumerate(value):
        record_label = f"{label}.provenance[{index}]"
        if not isinstance(record, dict):
            raise FolderModeError(f"{record_label} must be an object")
        _require_exact_keys(
            record,
            {"source_id", "source_file", "location", "relevant_date"},
            record_label,
        )
        source_id = _require_plain_text(record["source_id"], f"{record_label}.source_id", maximum=100)
        source_file = _require_plain_text(record["source_file"], f"{record_label}.source_file", maximum=2_000)
        if _is_absolute_or_unsafe_path(source_file):
            raise FolderModeError(f"{record_label}.source_file must be a safe relative path")
        location = _require_plain_text(record["location"], f"{record_label}.location", maximum=MAX_LOCATION_CODE_POINTS)
        relevant_date = record["relevant_date"]
        if relevant_date is not None:
            relevant_date = _require_plain_text(
                relevant_date, f"{record_label}.relevant_date", maximum=200
            )
        if source_id not in inventory_by_id:
            raise FolderModeError(f"{record_label} refers to an unknown source_id")
        inventory_row = inventory_by_id[source_id]
        if inventory_row["relative_path"] != source_file:
            raise FolderModeError(f"{record_label}.source_file does not match its source_id")
        if inventory_row["disposition"] != "included":
            raise FolderModeError(f"{record_label} refers to an excluded, unreadable or unsupported source")
        if inventory_row["read_status"] != "read":
            raise FolderModeError(
                f"{record_label} cannot be used as provenance until its inventory read_status is read"
            )
        identity = (source_id, location, relevant_date)
        if identity in seen:
            raise FolderModeError(f"{label}.provenance contains a duplicate source record")
        seen.add(identity)
        records.append(record)
    return records


def _validate_item(
    value: Any,
    label: str,
    expected_identifier: str,
    inventory_by_id: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FolderModeError(f"{label} must be an object")
    _require_exact_keys(
        value,
        {
            "item_id",
            "text",
            "confidence",
            "wording_basis",
            "review_status",
            "inference_approved",
            "provenance",
        },
        label,
    )
    item_id = _require_plain_text(value["item_id"], f"{label}.item_id", maximum=100)
    if item_id != expected_identifier:
        raise FolderModeError(f"{label}.item_id must be {expected_identifier}")
    _require_plain_text(value["text"], f"{label}.text", maximum=MAX_ITEM_CODE_POINTS)
    if value["confidence"] not in CONFIDENCE_VALUES:
        raise FolderModeError(f"{label}.confidence has an invalid value")
    if value["wording_basis"] not in WORDING_BASIS_VALUES:
        raise FolderModeError(f"{label}.wording_basis has an invalid value")
    if value["review_status"] not in REVIEW_STATUS_VALUES:
        raise FolderModeError(f"{label}.review_status has an invalid value")
    if type(value["inference_approved"]) is not bool:
        raise FolderModeError(f"{label}.inference_approved must be a boolean")
    if value["wording_basis"] != "inferred" and value["inference_approved"]:
        raise FolderModeError(f"{label}.inference_approved may be true only for inferred wording")
    _validate_provenance(value["provenance"], label, inventory_by_id)
    return value


def validate_draft(
    payload: Any,
    rows: Sequence[dict[str, str]],
    *,
    issue_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FolderModeError("briefing_draft.json must contain an object")
    _require_exact_keys(
        payload,
        {"schema_version", "mode", "context", "project_title", *LIST_FIELDS, "issues"},
        "briefing_draft.json",
    )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise FolderModeError("briefing_draft.json schema_version must be 1")
    if payload["mode"] != "research_folder":
        raise FolderModeError("briefing_draft.json mode must be research_folder")
    context = payload["context"]
    if not isinstance(context, dict):
        raise FolderModeError("briefing_draft.json context must be an object")
    _require_exact_keys(
        context,
        {"source_label", "reporting_period", "meeting_purpose", "attention_topics"},
        "briefing_draft.json context",
    )
    _require_plain_text(context["source_label"], "context.source_label", maximum=2_000)
    for key in ("reporting_period", "meeting_purpose"):
        if context[key] is not None:
            _require_plain_text(context[key], f"context.{key}", maximum=2_000)
    if not isinstance(context["attention_topics"], list):
        raise FolderModeError("context.attention_topics must be an array of text")
    for index, topic in enumerate(context["attention_topics"]):
        _require_plain_text(topic, f"context.attention_topics[{index}]", maximum=2_000)

    inventory_by_id = {row["source_id"]: row for row in rows}
    _validate_item(payload["project_title"], "project_title", "project_title", inventory_by_id)
    all_item_ids = {"project_title"}
    for field in LIST_FIELDS:
        values = payload[field]
        if not isinstance(values, list):
            raise FolderModeError(f"{field} must be an array")
        for index, value in enumerate(values, start=1):
            expected_identifier = f"{field}-{index}"
            _validate_item(value, f"{field}[{index - 1}]", expected_identifier, inventory_by_id)
            if expected_identifier in all_item_ids:
                raise FolderModeError(f"Duplicate item_id: {expected_identifier}")
            all_item_ids.add(expected_identifier)

    issues = payload["issues"]
    if not isinstance(issues, list):
        raise FolderModeError("issues must be an array")
    issue_ids: set[str] = set()
    for index, issue in enumerate(issues):
        label = f"issues[{index}]"
        if not isinstance(issue, dict):
            raise FolderModeError(f"{label} must be an object")
        _require_exact_keys(
            issue,
            {"issue_id", "type", "description", "source_ids", "status", "resolution"},
            label,
        )
        issue_id = _require_plain_text(issue["issue_id"], f"{label}.issue_id", maximum=100)
        if issue_id in issue_ids:
            raise FolderModeError(f"Duplicate issue_id: {issue_id}")
        issue_ids.add(issue_id)
        if issue["type"] not in ISSUE_TYPE_VALUES:
            raise FolderModeError(f"{label}.type has an invalid value")
        _require_plain_text(issue["description"], f"{label}.description", maximum=MAX_ISSUE_CODE_POINTS)
        if not isinstance(issue["source_ids"], list) or any(
            not isinstance(source_id, str) for source_id in issue["source_ids"]
        ):
            raise FolderModeError(f"{label}.source_ids must be an array of source IDs")
        if len(set(issue["source_ids"])) != len(issue["source_ids"]):
            raise FolderModeError(f"{label}.source_ids contains a duplicate")
        known_issue_sources = set(inventory_by_id)
        if issue_source_ids is not None:
            known_issue_sources.update(issue_source_ids)
        unknown_sources = sorted(set(issue["source_ids"]) - known_issue_sources)
        if unknown_sources:
            raise FolderModeError(f"{label}.source_ids contains an unknown source")
        if issue["status"] not in ISSUE_STATUS_VALUES:
            raise FolderModeError(f"{label}.status has an invalid value")
        resolution = issue["resolution"]
        if issue["status"] in {"accepted", "resolved"}:
            _require_plain_text(resolution, f"{label}.resolution", maximum=MAX_ISSUE_CODE_POINTS)
        elif resolution is not None and resolution != "":
            _require_plain_text(resolution, f"{label}.resolution", maximum=MAX_ISSUE_CODE_POINTS)
    return payload


def _verify_review_file_set(review_directory: Path) -> None:
    if not review_directory.is_dir():
        raise FolderModeError("Review directory does not exist")
    actual = {path.name for path in review_directory.iterdir()}
    expected = set(REVIEW_FILE_NAMES)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        messages: list[str] = []
        if missing:
            messages.append("missing " + ", ".join(missing))
        if extra:
            messages.append("unexpected " + ", ".join(extra))
        raise FolderModeError("Review directory must contain exactly five artefacts (" + "; ".join(messages) + ")")


def _verify_inventory_against_source(
    source: Path,
    recorded_rows: Sequence[dict[str, str]],
    exclusion_patterns: Sequence[str],
) -> list[dict[str, str]]:
    live_rows = inventory_source(source, exclusion_patterns)
    recorded = {row["relative_path"]: row for row in recorded_rows}
    live = {row["relative_path"]: row for row in live_rows}
    if set(recorded) != set(live):
        added = sorted(set(live) - set(recorded))
        removed = sorted(set(recorded) - set(live))
        details: list[str] = []
        if added:
            details.append("added " + ", ".join(added))
        if removed:
            details.append("removed " + ", ".join(removed))
        raise FolderModeError("Source set changed after inventory (" + "; ".join(details) + ")")
    for relative_path in sorted(recorded):
        stored = recorded[relative_path]
        current = live[relative_path]
        if stored["source_id"] != current["source_id"]:
            raise FolderModeError(f"Source identifier changed for {relative_path}")
        if stored["size_bytes"] != current["size_bytes"]:
            raise FolderModeError(f"Source size changed for {relative_path}")
        if stored["sha256"] != current["sha256"]:
            raise FolderModeError(f"Source hash changed for {relative_path}")
        if stored["modified_at"] != current["modified_at"]:
            raise FolderModeError(f"Source modified_at changed for {relative_path}")
        for key in (
            "detected_type",
            "duplicate_group",
            "version_group",
            "version_role",
            "version_ambiguous",
            "confidentiality_flag",
        ):
            if stored[key] != current[key]:
                raise FolderModeError(
                    f"Mechanical inventory field {key} changed for {relative_path}"
                )
        if stored["disposition"] != current["disposition"]:
            raise FolderModeError(f"Inventory disposition changed for {relative_path}")
        if (
            stored["disposition"] != "included"
            and stored["read_status"] != current["read_status"]
        ):
            raise FolderModeError(f"Inventory read status changed invalidly for {relative_path}")
    return live_rows


def _validate_mechanical_issues(
    draft: dict[str, Any],
    recorded_rows: Sequence[dict[str, str]],
    unresolved_path: Path,
) -> None:
    """Keep inventory-generated risks visible throughout the review gate."""
    required = initial_issues(recorded_rows, draft["context"]["reporting_period"])
    submitted = {issue["issue_id"]: issue for issue in draft["issues"]}
    try:
        unresolved_text = unresolved_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FolderModeError(f"Could not read unresolved_items.md: {exc}") from exc

    immutable_keys = ("type", "description", "source_ids")
    for mechanical in required:
        issue_id = mechanical["issue_id"]
        issue_type = mechanical["type"]
        candidate = submitted.get(issue_id)
        if candidate is None:
            raise FolderModeError(
                "A mechanical inventory issue was deleted from briefing_draft.json: "
                f"{issue_id} ({issue_type})"
            )
        if any(candidate[key] != mechanical[key] for key in immutable_keys):
            raise FolderModeError(
                "A mechanical inventory issue was altered in briefing_draft.json: "
                f"{issue_id} ({issue_type})"
            )
        marker = f"{issue_id} — {issue_type}"
        if marker not in unresolved_text:
            raise FolderModeError(
                "A mechanical inventory issue is missing from unresolved_items.md: "
                f"{issue_id} ({issue_type})"
            )


def validate_review(
    source: Path,
    review_directory: Path,
    *,
    excludes: Sequence[str] = (),
) -> tuple[str, dict[str, Any], list[dict[str, str]]]:
    _verify_review_file_set(review_directory)
    recorded_rows = load_inventory(review_directory)
    live_rows = _verify_inventory_against_source(source, recorded_rows, excludes)
    mechanical_rows = inventory_source(source, ())
    draft = validate_draft(
        load_json(review_directory / "briefing_draft.json", "briefing draft"),
        recorded_rows,
        issue_source_ids={row["source_id"] for row in mechanical_rows},
    )
    _validate_mechanical_issues(
        draft,
        mechanical_rows,
        review_directory / "unresolved_items.md",
    )

    source_absolute = str(source.resolve())
    for name in REVIEW_FILE_NAMES:
        try:
            data = (review_directory / name).read_bytes()
        except OSError as exc:
            raise FolderModeError(f"Could not read review artefact {name}: {exc}") from exc
        decoded = data.decode("utf-8", errors="ignore")
        if source_absolute in decoded or _contains_absolute_path(decoded):
            raise FolderModeError(f"Review artefact {name} exposes an absolute or file URL path")

    digest = hashlib.sha256()
    digest.update(REVIEW_DIGEST_DOMAIN)
    for name in sorted(REVIEW_FILE_NAMES):
        data = (review_directory / name).read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    source_fingerprint = [
        {
            "relative_path": row["relative_path"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
        }
        for row in live_rows
    ]
    digest.update(canonical_json_bytes(source_fingerprint))
    return digest.hexdigest(), draft, recorded_rows


def load_approval(path: Path) -> dict[str, Any]:
    payload = load_json(path, "approval JSON")
    if not isinstance(payload, dict):
        raise FolderModeError("Approval JSON must contain an object")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "review_digest",
            "approve_finalisation",
            "approved_inferred_item_ids",
            "acknowledged_issue_ids",
        },
        "approval JSON",
    )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise FolderModeError("Approval schema_version must be 1")
    if not isinstance(payload["review_digest"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", payload["review_digest"]
    ):
        raise FolderModeError("Approval review_digest must be a lowercase SHA-256")
    if payload["approve_finalisation"] is not True:
        raise FolderModeError("Approval must explicitly set approve_finalisation to true")
    for key in ("approved_inferred_item_ids", "acknowledged_issue_ids"):
        values = payload[key]
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            raise FolderModeError(f"Approval {key} must be an array of non-empty text")
        if len(set(values)) != len(values):
            raise FolderModeError(f"Approval {key} contains a duplicate")
    return payload


def _all_draft_items(draft: dict[str, Any]) -> list[dict[str, Any]]:
    return [draft["project_title"], *(item for field in LIST_FIELDS for item in draft[field])]


def enforce_review_gate(
    draft: dict[str, Any],
    digest: str,
    approval: dict[str, Any] | None,
    *,
    allow_unconfirmed: bool,
) -> str:
    if approval is not None and allow_unconfirmed:
        raise FolderModeError("Use either an approval file or --allow-unconfirmed, not both")
    if approval is None and not allow_unconfirmed:
        raise FolderModeError("Researcher approval is required before finalisation")

    included_items = [item for item in _all_draft_items(draft) if item["review_status"] != "removed"]
    if draft["project_title"]["review_status"] == "removed":
        raise FolderModeError("Project title cannot be removed from the final briefing")

    if approval is not None:
        if approval["review_digest"] != digest:
            raise FolderModeError("Approval digest does not match the current review artefacts and sources")
        pending = [item["item_id"] for item in _all_draft_items(draft) if item["review_status"] == "pending"]
        if pending:
            raise FolderModeError("Pending briefing items remain: " + ", ".join(pending))
        open_issues = [issue["issue_id"] for issue in draft["issues"] if issue["status"] == "open"]
        if open_issues:
            raise FolderModeError("Open issues remain: " + ", ".join(open_issues))
        inferred = {
            item["item_id"]
            for item in included_items
            if item["wording_basis"] == "inferred"
        }
        approved_inferred = set(approval["approved_inferred_item_ids"])
        if approved_inferred != inferred:
            missing = sorted(inferred - approved_inferred)
            extra = sorted(approved_inferred - inferred)
            details: list[str] = []
            if missing:
                details.append("unapproved inferred items " + ", ".join(missing))
            if extra:
                details.append("unknown or non-final inferred items " + ", ".join(extra))
            raise FolderModeError("Inferred-item approval mismatch: " + "; ".join(details))
        without_internal_approval = sorted(
            item["item_id"]
            for item in included_items
            if item["wording_basis"] == "inferred" and not item["inference_approved"]
        )
        if without_internal_approval:
            raise FolderModeError(
                "Inferred items also require inference_approved=true: "
                + ", ".join(without_internal_approval)
            )
        accepted_issue_ids = {
            issue["issue_id"] for issue in draft["issues"] if issue["status"] == "accepted"
        }
        acknowledged = set(approval["acknowledged_issue_ids"])
        if acknowledged != accepted_issue_ids:
            missing = sorted(accepted_issue_ids - acknowledged)
            extra = sorted(acknowledged - accepted_issue_ids)
            details = []
            if missing:
                details.append("unacknowledged issues " + ", ".join(missing))
            if extra:
                details.append("unknown or non-accepted issues " + ", ".join(extra))
            raise FolderModeError("Issue acknowledgement mismatch: " + "; ".join(details))
        return "approved"

    inferred_without_permission = sorted(
        item["item_id"]
        for item in included_items
        if item["wording_basis"] == "inferred"
    )
    if inferred_without_permission:
        raise FolderModeError(
            "Unconfirmed generation cannot include inferred items; remove them or use a digest-bound approval: "
            + ", ".join(inferred_without_permission)
        )
    return "unconfirmed"


def final_payload_and_mapping(
    draft: dict[str, Any], *, review_status: str
) -> tuple[dict[str, Any], dict[str, tuple[str, dict[str, Any]]]]:
    include_statuses = {"approved"} if review_status == "approved" else {"approved", "pending"}
    if draft["project_title"]["review_status"] not in include_statuses:
        raise FolderModeError("Project title is not available for final generation")
    payload: dict[str, Any] = {"project_title": draft["project_title"]["text"]}
    mapping: dict[str, tuple[str, dict[str, Any]]] = {
        "project_title": ("project_title", draft["project_title"])
    }
    for field in LIST_FIELDS:
        final_items = [item for item in draft[field] if item["review_status"] in include_statuses]
        payload[field] = [item["text"] for item in final_items]
        for index, item in enumerate(final_items, start=1):
            mapping[item["item_id"]] = (f"{field}-{index}", item)
    return payload, mapping


def _evidence_version_status(row: dict[str, str]) -> str:
    if row["duplicate_group"]:
        return "duplicate"
    if row["version_ambiguous"] == "true" or row["version_role"] == "competing_current_candidate":
        return "uncertain"
    if row["version_role"] == "current_candidate":
        return "current_candidate"
    if row["version_role"] == "previous":
        return "previous"
    return "single"


def _evidence_issue_type(issue_type: str) -> str:
    return {
        "classification_uncertainty": "classification_uncertainty",
        "competing_versions": "version_conflict",
        "confidentiality_risk": "confidentiality_risk",
        "duplicate_version": "version_conflict",
        "interpretation_uncertainty": "interpretation_uncertainty",
        "missing_reporting_period": "other",
        "numerical_conflict": "numerical_conflict",
        "other": "other",
        "possible_confidentiality": "confidentiality_risk",
        "unclear_date": "date_uncertainty",
        "unclear_owner": "ownership_uncertainty",
        "unreadable_source": "unsupported_source",
        "unsupported_file": "unsupported_source",
    }[issue_type]


def _unshareable_source_labels(
    rows: Sequence[dict[str, str]], shareable_source_ids: set[str]
) -> set[str]:
    """Return relative file paths and basenames that must not leak publicly."""
    labels: set[str] = set()
    for row in rows:
        if row["detected_type"] == "Directory":
            if row["disposition"] != "excluded":
                continue
            directory_name = PurePosixPath(row["relative_path"]).name
            if not (
                row["reason"].startswith("Explicit user exclusion:")
                or _confidentiality_flag(directory_name)
            ):
                # Generic cache and generated-output directory labels such as
                # "build" are ordinary research prose and are not private
                # source filenames by themselves.
                continue
        if (
            row["source_id"] in shareable_source_ids
            and row["disposition"] == "included"
            and row["read_status"] == "read"
        ):
            continue
        relative_path = unicodedata.normalize("NFC", row["relative_path"]).casefold()
        labels.add(relative_path)
        labels.add(PurePosixPath(relative_path).name)
    return {label for label in labels if label}


def _mentioned_source_label(values: Sequence[str | None], labels: set[str]) -> str | None:
    for value in values:
        if not value:
            continue
        folded = unicodedata.normalize("NFC", value).casefold()
        for label in sorted(labels, key=lambda candidate: (-len(candidate), candidate)):
            if re.search(
                rf"(?<![\w.-]){re.escape(label)}(?![\w-])",
                folded,
            ):
                return label
    return None


def build_evidence_manifest(
    payload: dict[str, Any],
    draft: dict[str, Any],
    rows: Sequence[dict[str, str]],
    mapping: dict[str, tuple[str, dict[str, Any]]],
    *,
    review_status: str,
) -> dict[str, Any]:
    rows_by_id = {row["source_id"]: row for row in rows}
    item_source_ids: set[str] = set()
    items: dict[str, Any] = {}
    original_to_final: dict[str, str] = {}
    item_sources: dict[str, set[str]] = {}
    for original_id, (final_id, item) in mapping.items():
        original_to_final[original_id] = final_id
        references = []
        sources_for_item: set[str] = set()
        for reference in item["provenance"]:
            source_id = reference["source_id"]
            item_source_ids.add(source_id)
            sources_for_item.add(source_id)
            references.append(
                {
                    "source_id": source_id,
                    "location": reference["location"],
                    "relevant_date": reference["relevant_date"],
                }
            )
        item_sources[final_id] = sources_for_item
        items[final_id] = {
            "wording_basis": item["wording_basis"],
            "confidence": item["confidence"],
            "explicitly_approved": review_status == "approved",
            "text_sha256": hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
            "references": references,
        }

    for original_id, (final_id, item) in mapping.items():
        unshareable_labels = _unshareable_source_labels(
            rows, item_sources[final_id]
        )
        mentioned_label = _mentioned_source_label(
            [
                item["text"],
                *(
                    value
                    for reference in item["provenance"]
                    for value in (reference["location"], reference["relevant_date"])
                ),
            ],
            unshareable_labels,
        )
        if mentioned_label is not None:
            raise FolderModeError(
                f"Final briefing item {original_id} references an uncited or "
                f"unshareable source filename: {mentioned_label}"
            )

    sources = []
    for source_id in sorted(item_source_ids, key=lambda value: rows_by_id[value]["relative_path"].casefold()):
        row = rows_by_id[source_id]
        sources.append(
            {
                "source_id": source_id,
                "display_path": row["relative_path"],
                "file_type": row["detected_type"],
                "modified_at": row["modified_at"] or None,
                "version_status": _evidence_version_status(row),
                "read_status": "read",
            }
        )

    evidence_issues = []
    for issue in draft["issues"]:
        issue_sources = set(issue["source_ids"])
        if (
            not issue_sources
            or not issue_sources.issubset(item_source_ids)
            or any(
                source_id not in rows_by_id
                or rows_by_id[source_id]["disposition"] != "included"
                or rows_by_id[source_id]["read_status"] != "read"
                for source_id in issue_sources
            )
        ):
            # Mixed, excluded and issue-only sources remain in the private
            # review artefacts. They must not leak through the shareable HTML
            # or final source map merely because one source also supports an
            # included briefing item.
            continue
        issue_unshareable_labels = _unshareable_source_labels(rows, issue_sources)
        if _mentioned_source_label(
            [issue["description"], issue["resolution"]], issue_unshareable_labels
        ) is not None:
            continue
        linked_items = sorted(
            final_id for final_id, sources_for_item in item_sources.items() if sources_for_item & issue_sources
        )
        if not linked_items:
            continue
        issue_status = issue["status"]
        issue_resolution = issue["resolution"]
        if review_status == "unconfirmed":
            issue_status = "open"
            issue_resolution = "Not researcher-confirmed; retained for review."
        evidence_issues.append(
            {
                "issue_id": issue["issue_id"],
                "type": _evidence_issue_type(issue["type"]),
                "description": issue["description"],
                "status": issue_status,
                "resolution": issue_resolution
                or "Not resolved; retained in the unconfirmed draft for researcher review.",
                "item_ids": linked_items,
                "source_ids": sorted(issue_sources & item_source_ids),
            }
        )

    brief_id = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return {
        "schema_version": 1,
        "brief_id": brief_id,
        "review_status": "approved" if review_status == "approved" else "automatic_unconfirmed",
        "sources": sources,
        "items": items,
        "issues": evidence_issues,
    }


def final_source_map_markdown(
    mapping: dict[str, tuple[str, dict[str, Any]]],
    evidence: dict[str, Any],
    *,
    review_status: str,
) -> str:
    introduction = (
        "This map records only final briefing content and approved relative source locations. "
        "It contains no source excerpts."
        if review_status == "approved"
        else "This map records unconfirmed draft content and relative source locations for "
        "researcher review. It contains no source excerpts."
    )
    lines = [
        "# Final source map",
        "",
        introduction,
        "",
    ]
    for final_id, item in mapping.values():
        lines.extend(
            (
                f"## {FIELD_LABELS['project_title'] if final_id == 'project_title' else FIELD_LABELS[final_id.rsplit('-', 1)[0]]}: `{final_id}`",
                "",
                item["text"],
                "",
                f"- Confidence: `{item['confidence']}`",
                f"- Wording basis: `{item['wording_basis']}`",
                "- Sources:",
            )
        )
        for reference in item["provenance"]:
            date_text = f"; date: {reference['relevant_date']}" if reference["relevant_date"] else ""
            lines.append(
                f"  - `{reference['source_file']}` — {reference['location']}{date_text}"
            )
        lines.append("")
    evidence_issues = evidence["issues"]
    if evidence_issues:
        statuses = {issue["status"] for issue in evidence_issues}
        has_active_boundaries = bool(statuses & {"open", "accepted"})
        has_resolved = "resolved" in statuses
        if has_active_boundaries and has_resolved:
            issue_heading = (
                "Accepted evidence boundaries and resolved issues"
                if review_status == "approved"
                else "Evidence boundaries requiring review and resolved issues"
            )
        elif has_resolved:
            issue_heading = "Resolved evidence issues"
        else:
            issue_heading = (
                "Accepted evidence boundaries"
                if review_status == "approved"
                else "Evidence boundaries requiring review"
            )
        lines.extend(
            (
                f"## {issue_heading}",
                "",
            )
        )
        for issue in evidence_issues:
            lines.append(
                f"- **{issue['issue_id']} ({issue['status']})**: {issue['description']} "
                f"Resolution: {issue['resolution'] or 'Not resolved.'}"
            )
        lines.append("")
    return "\n".join(lines)


def validation_report_markdown(
    *,
    review_status: str,
    digest: str,
    payload: dict[str, Any],
    html_source: str,
    source: Path,
) -> str:
    item_count = 1 + sum(len(payload[field]) for field in LIST_FIELDS)
    item_texts = [payload["project_title"], *(item for field in LIST_FIELDS for item in payload[field])]
    visible_html = re.sub(
        r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
        " ",
        html_source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    visible_html = html.unescape(re.sub(r"<[^>]+>", " ", visible_html))
    checks = [
        ("Stable eight-field input schema", set(payload) == {"project_title", *LIST_FIELDS}),
        ("Briefing item reconciliation", item_count >= 1),
        ("Every final item rendered", all(html.escape(item, quote=True) in html_source for item in item_texts)),
        ("Evidence Explorer rendered", 'id="group-evidence"' in html_source and "Evidence Explorer" in html_source),
        ("Search and navigation controls rendered", 'id="workspace-search"' in html_source and 'class="sidebar-nav"' in html_source),
        ("Print support rendered", 'id="print-briefing"' in html_source and "@media print" in html_source),
        ("No external web dependency", re.search(r'(?:src|href)=["\'](?:https?:)?//', html_source, re.I) is None),
        ("No file URL", "file://" not in html_source.casefold()),
        ("No local absolute path", not _contains_absolute_path(visible_html)),
        ("All workspace sections present", all(f'id="group-{identifier}"' in html_source for identifier in ("overview", "progress_evidence", "discussion", "actions_timeline", "evidence"))),
    ]
    if not all(passed for _, passed in checks):
        failed = ", ".join(label for label, passed in checks if not passed)
        raise FolderModeError(f"Generated HTML failed validation: {failed}")
    lines = [
        "# Final Folder Mode validation report",
        "",
        "**Automated validation: PASS**",
        "",
        f"- Review status: `{review_status}`",
        f"- Review digest: `{digest}`",
        f"- Final briefing items including title: {item_count}",
        "- Rendering layer: existing deterministic `build_briefing.py` builder",
        "- Evidence Explorer: included",
        "",
        "## Automated checks",
        "",
    ]
    lines.extend(f"- {'PASS' if passed else 'FAIL'} — {label}" for label, passed in checks)
    lines.extend(
        (
            "",
            "## Browser verification still required",
            "",
            "Open `final_briefing.html` locally and verify search, navigation, meeting-state controls and print preview in the available browser.",
            "",
        )
    )
    if review_status == "unconfirmed":
        lines.insert(4, "- Warning: the briefing was generated with the explicit unconfirmed-review bypass.")
    return "\n".join(lines)


def finalise(
    source: Path,
    review_directory: Path,
    final_directory: Path,
    *,
    approval_path: Path | None,
    allow_unconfirmed: bool,
    excludes: Sequence[str] = (),
) -> None:
    _ensure_output_is_outside_source(source, final_directory)
    if final_directory.exists():
        raise FolderModeError("Final directory already exists; remove it or choose a new path")
    digest, draft, rows = validate_review(
        source, review_directory, excludes=excludes
    )
    approval = load_approval(approval_path) if approval_path is not None else None
    review_status = enforce_review_gate(
        draft, digest, approval, allow_unconfirmed=allow_unconfirmed
    )
    payload, mapping = final_payload_and_mapping(draft, review_status=review_status)
    evidence = build_evidence_manifest(
        payload, draft, rows, mapping, review_status=review_status
    )

    final_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final_directory.name}.", dir=final_directory.parent))
    try:
        # Resolve subprocess paths before changing its working directory. This
        # keeps documented relative SOURCE, REVIEW_DIR and FINAL_DIR commands
        # reliable when the caller starts from the repository root.
        builder_input = (staging / ".builder_input.json").resolve()
        evidence_input = (staging / ".evidence_manifest.json").resolve()
        builder_input.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        evidence_input.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        command = [
            sys.executable,
            str(BUILDER),
            str(builder_input),
            str((staging / "final_briefing.html").resolve()),
            "--evidence",
            str(evidence_input),
        ]
        if review_status == "unconfirmed":
            unconfirmed_config = (staging / ".unconfirmed_config.json").resolve()
            unconfirmed_config.write_text(
                json.dumps({"briefing_label": "Unconfirmed draft"}) + "\n",
                encoding="utf-8",
            )
            command.extend(("--config", str(unconfirmed_config)))
        result = subprocess.run(
            command,
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown builder error"
            raise FolderModeError(f"Deterministic HTML builder failed: {message}")

        (staging / "final_briefing_input.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "final_source_map.md").write_text(
            final_source_map_markdown(
                mapping,
                evidence,
                review_status=review_status,
            ),
            encoding="utf-8",
        )
        html_source = (staging / "final_briefing.html").read_text(encoding="utf-8")
        (staging / "final_validation_report.md").write_text(
            validation_report_markdown(
                review_status=review_status,
                digest=digest,
                payload=payload,
                html_source=html_source,
                source=source,
            ),
            encoding="utf-8",
        )
        for temporary_name in (
            ".builder_input.json",
            ".evidence_manifest.json",
            ".unconfirmed_config.json",
        ):
            (staging / temporary_name).unlink(missing_ok=True)
        actual = {path.name for path in staging.iterdir()}
        if actual != set(FINAL_FILE_NAMES):
            raise FolderModeError("Internal error: final staging set is incomplete")
        os.replace(staging, final_directory)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory and finalise source-grounded supervisor briefings."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory", help="Create the five review artefacts")
    inventory_parser.add_argument("source", type=Path)
    inventory_parser.add_argument("review_directory", type=Path)
    inventory_parser.add_argument("--reporting-period")
    inventory_parser.add_argument("--meeting-purpose")
    inventory_parser.add_argument("--attention-topic", action="append", default=[])
    inventory_parser.add_argument("--exclude", action="append", default=[])

    validate_parser = subparsers.add_parser("validate-review", help="Validate and digest the review set")
    validate_parser.add_argument("source", type=Path)
    validate_parser.add_argument("review_directory", type=Path)
    validate_parser.add_argument("--exclude", action="append", default=[])

    finalise_parser = subparsers.add_parser("finalise", help="Create the four final artefacts")
    finalise_parser.add_argument("source", type=Path)
    finalise_parser.add_argument("review_directory", type=Path)
    finalise_parser.add_argument("final_directory", type=Path)
    finalise_parser.add_argument("--approval", type=Path)
    finalise_parser.add_argument("--allow-unconfirmed", action="store_true")
    finalise_parser.add_argument("--exclude", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "inventory":
            create_inventory(
                arguments.source,
                arguments.review_directory,
                reporting_period=arguments.reporting_period,
                meeting_purpose=arguments.meeting_purpose,
                attention_topics=arguments.attention_topic,
                excludes=arguments.exclude,
            )
        elif arguments.command == "validate-review":
            digest, _, _ = validate_review(
                arguments.source,
                arguments.review_directory,
                excludes=arguments.exclude,
            )
            print(digest)
        elif arguments.command == "finalise":
            finalise(
                arguments.source,
                arguments.review_directory,
                arguments.final_directory,
                approval_path=arguments.approval,
                allow_unconfirmed=arguments.allow_unconfirmed,
                excludes=arguments.exclude,
            )
        else:  # pragma: no cover - argparse enforces the subcommand set.
            raise FolderModeError("Unknown Folder Mode command")
    except FolderModeError as exc:
        print(f"Folder Mode input error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Folder Mode system error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
