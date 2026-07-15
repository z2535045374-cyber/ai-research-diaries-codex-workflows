#!/usr/bin/env python3
"""Validate public links, offline assets, privacy boundaries and packaging."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_HTML = (
    REPOSITORY_ROOT / "index.html",
    REPOSITORY_ROOT / "404.html",
    REPOSITORY_ROOT
    / "research-briefing-dashboard"
    / "examples"
    / "meeting_brief.html",
)
MARKDOWN_FILES = (
    REPOSITORY_ROOT / "README.md",
    REPOSITORY_ROOT / "CUSTOMISING.md",
    REPOSITORY_ROOT / "CONTRIBUTING.md",
    REPOSITORY_ROOT / "CONTENT-LICENSE.md",
    REPOSITORY_ROOT / "FOLDER_MODE_DESIGN.md",
    REPOSITORY_ROOT / "FOLDER_MODE_TEST_RESULTS.md",
    REPOSITORY_ROOT / "CHANGELOG.md",
    REPOSITORY_ROOT / "research-briefing-dashboard" / "SKILL.md",
    REPOSITORY_ROOT / "research-briefing-dashboard" / "CONTENT-LICENSE.md",
)
TEXT_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}
PUBLIC_TEXT_NAMES = {".gitignore", "LICENSE"}
EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel"}
TARGET_RELEASE = "1.2.0"
TARGET_WEBSITE_VERSION = "1.2"
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
REQUIRED_V12_PACKAGE_MEMBERS = {
    "examples/folder-mode/EXAMPLE_NOTES.md",
    "examples/folder-mode/final/final_briefing.html",
    "examples/folder-mode/final/final_briefing_input.json",
    "examples/folder-mode/final/final_source_map.md",
    "examples/folder-mode/final/final_validation_report.md",
    "examples/folder-mode/review/briefing_draft.json",
    "examples/folder-mode/review/excluded_files.md",
    "examples/folder-mode/review/source_inventory.csv",
    "examples/folder-mode/review/source_map.md",
    "examples/folder-mode/review/unresolved_items.md",
    "package_manifest.txt",
    "scripts/folder_mode.py",
    "tests/test_folder_mode.py",
}
AMERICAN_TO_BRITISH = {
    "acknowledgment": "acknowledgement",
    "analyze": "analyse",
    "analyzed": "analysed",
    "analyzing": "analysing",
    "artifact": "artefact",
    "artifacts": "artefacts",
    "behavior": "behaviour",
    "behaviors": "behaviours",
    "canceled": "cancelled",
    "catalog": "catalogue",
    "catalogs": "catalogues",
    "centered": "centred",
    "centering": "centring",
    "customization": "customisation",
    "customize": "customise",
    "customized": "customised",
    "defense": "defence",
    "favor": "favour",
    "favorite": "favourite",
    "fulfill": "fulfil",
    "gray": "grey",
    "honor": "honour",
    "labeled": "labelled",
    "labeling": "labelling",
    "modeling": "modelling",
    "neighbor": "neighbour",
    "organize": "organise",
    "organized": "organised",
    "organizing": "organising",
    "prioritize": "prioritise",
    "sanitize": "sanitise",
    "sanitized": "sanitised",
    "summarize": "summarise",
    "summarized": "summarised",
    "toward": "towards",
    "traveled": "travelled",
    "visualize": "visualise",
    "visualized": "visualised",
}
PRIVACY_PATTERNS = {
    "email address": re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    ),
    "macOS user path": re.compile(r"/Users/[^\s<>'\"]+"),
    "Windows user path": re.compile(r"[A-Z]:\\Users\\[^\s<>'\"]+", re.IGNORECASE),
    "local file URL": re.compile(
        r"\bfile:///(?:Users|home|private|tmp|[A-Z]:)[^\s<>'\"]+",
        re.IGNORECASE,
    ),
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "AWS-style access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
POSIX_ABSOLUTE_PATH_IN_PROSE_PATTERN = re.compile(
    r"(?<![\w._/\\-])/(?!\s)[^\s<>'\"`]+"
)
UNC_ABSOLUTE_PATH_IN_PROSE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_\\])\\\\[^\\\s]+\\[^\\\s]+"
)
HOME_DIRECTORY_PATH_IN_PROSE_PATTERN = re.compile(
    r"(?<![\w._-])~(?:"
    r"[A-Za-z][A-Za-z0-9._-]*(?=$|[\s,;:)\]}])"
    r"|(?:[A-Za-z0-9._-]+)?[/\\][^\s<>'\"`]+"
    r")"
)
NETWORK_URL_IN_PROSE_PATTERN = re.compile(
    r"\bhttps?://[^\s<>'\"`]+",
    re.IGNORECASE,
)
FORBIDDEN_ARCHIVE_PARTS = {
    ".DS_Store",
    ".pytest_cache",
    ".superpowers",
    "__MACOSX",
    "__pycache__",
}


class PublicationError(RuntimeError):
    """Collect a publication validation failure."""


def load_packager():
    """Load the archive builder without relying on the caller's import path."""
    path = REPOSITORY_ROOT / "scripts" / "package_skill.py"
    specification = importlib.util.spec_from_file_location(
        "publication_package_skill",
        path,
    )
    if specification is None or specification.loader is None:
        raise PublicationError("Could not load scripts/package_skill.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def published_html_files() -> tuple[Path, ...]:
    """Return every public page and packaged, generated HTML example."""
    pages = list(PUBLISHED_HTML)
    try:
        package_sources = load_packager().source_files()
    except (OSError, ValueError) as exc:
        raise PublicationError(f"Skill package allow-list failed: {exc}") from exc
    pages.extend(
        source
        for source in package_sources
        if source.suffix.lower() in {".htm", ".html"}
        and "examples" in source.relative_to(
            REPOSITORY_ROOT / "research-briefing-dashboard"
        ).parts
    )
    return tuple(dict.fromkeys(path.resolve() for path in pages))


def publication_markdown_files() -> tuple[Path, ...]:
    """Return root documentation and every Markdown file in the Skill package."""
    documents = list(MARKDOWN_FILES)
    try:
        package_sources = load_packager().source_files()
    except (OSError, ValueError) as exc:
        raise PublicationError(f"Skill package allow-list failed: {exc}") from exc
    documents.extend(
        source for source in package_sources if source.suffix.lower() == ".md"
    )
    return tuple(dict.fromkeys(path.resolve() for path in documents))


class PageInventory(HTMLParser):
    """Collect identifiers, links, visible prose and runtime dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.identifiers: set[str] = set()
        self.references: list[tuple[str, str, str]] = []
        self.visible_text: list[str] = []
        self.forms = 0
        self._hidden_text_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        attribute_map = dict(attributes)
        identifier = attribute_map.get("id")
        if identifier:
            self.identifiers.add(identifier)
        for attribute in ("href", "src", "srcset", "poster", "data", "action"):
            value = attribute_map.get(attribute)
            if value:
                self.references.append((tag, attribute, value))
        if tag in {"script", "style", "template"}:
            self._hidden_text_depth += 1
        if tag == "form":
            self.forms += 1

    def handle_startendtag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attributes)
        if tag in {"script", "style", "template"}:
            self._hidden_text_depth -= 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template"} and self._hidden_text_depth:
            self._hidden_text_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden_text_depth == 0 and data.strip():
            self.visible_text.append(data)


def public_inventory() -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        REPOSITORY_ROOT / relative
        for relative in result.stdout.decode("utf-8").split("\0")
        if relative
    ]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PublicationError(f"Could not read {path.relative_to(REPOSITORY_ROOT)}: {exc}") from exc


def parse_html(path: Path) -> tuple[str, PageInventory]:
    source = read_text(path)
    parser = PageInventory()
    parser.feed(source)
    parser.close()
    return source, parser


def local_target(source_path: Path, value: str) -> tuple[Path | None, str]:
    split = urlsplit(value)
    if split.scheme.lower() in EXTERNAL_SCHEMES or split.netloc:
        return None, ""
    if value.startswith("data:") or value.startswith("javascript:"):
        return None, ""
    if split.path.startswith("/"):
        return None, split.fragment
    target = source_path.parent / unquote(split.path) if split.path else source_path
    return target.resolve(), split.fragment


def reference_values(attribute: str, value: str) -> list[str]:
    """Return individual URLs from a normal reference or ``srcset``."""
    if attribute != "srcset":
        return [value]
    if "data:" in value.lower():
        raise PublicationError("data URLs in srcset are not supported by publication validation")
    return [
        candidate.strip().split()[0]
        for candidate in value.split(",")
        if candidate.strip()
    ]


def runtime_dependency_issues(source: str, inventory: PageInventory) -> list[str]:
    """Detect network APIs and external runtime resources in HTML source."""
    issues: list[str] = []
    if re.search(
        r"(?:\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b|\bEventSource\b)",
        source,
    ):
        issues.append("contains a network runtime API")
    if re.search(
        r"@import\s+(?:url\(\s*)?['\"]?(?:https?:)?//",
        source,
        re.IGNORECASE,
    ):
        issues.append("contains an external CSS import")
    if re.search(
        r"url\(\s*['\"]?(?:https?:)?//",
        source,
        re.IGNORECASE,
    ):
        issues.append("contains an external CSS asset")

    for tag, attribute, value in inventory.references:
        try:
            values = reference_values(attribute, value)
        except PublicationError as exc:
            issues.append(str(exc))
            continue
        for candidate in values:
            split = urlsplit(candidate)
            is_external = split.scheme.lower() in EXTERNAL_SCHEMES or bool(split.netloc)
            is_runtime_reference = (
                attribute in {"src", "srcset", "poster", "data", "action"}
                or tag == "link"
            )
            if is_external and is_runtime_reference:
                issues.append(f"contains external runtime dependency {candidate!r}")
    return issues


def validate_html(path: Path) -> PageInventory:
    source, inventory = parse_html(path)
    relative = path.relative_to(REPOSITORY_ROOT) if path.is_relative_to(REPOSITORY_ROOT) else path
    issues: list[str] = []
    if re.search(r"\{\{[^{}]+\}\}", source):
        issues.append("contains an unresolved template token")
    if inventory.forms:
        issues.append("contains a form")
    issues.extend(runtime_dependency_issues(source, inventory))

    for tag, attribute, value in inventory.references:
        try:
            values = reference_values(attribute, value)
        except PublicationError:
            continue
        for candidate in values:
            target, fragment = local_target(path, candidate)
            if target is None:
                continue
            if not target.exists():
                issues.append(f"has missing relative target {candidate!r}")
                continue
            if fragment and target.suffix.lower() in {"", ".html", ".htm"}:
                _, target_inventory = parse_html(target)
                if fragment not in target_inventory.identifiers:
                    issues.append(f"has missing fragment target {candidate!r}")

    if issues:
        raise PublicationError(f"{relative}: " + "; ".join(sorted(set(issues))))
    return inventory


def validate_markdown_links(path: Path) -> None:
    source = read_text(path)
    issues: list[str] = []
    for match in re.finditer(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", source):
        value = match.group(1).strip()
        if value.startswith("<") and value.endswith(">"):
            value = value[1:-1]
        target, _ = local_target(path, value)
        if target is not None and not target.exists():
            issues.append(value)
    if issues:
        relative = path.relative_to(REPOSITORY_ROOT)
        raise PublicationError(
            f"{relative}: missing Markdown target(s): {', '.join(sorted(set(issues)))}"
        )


def prose_from_markdown(path: Path) -> str:
    source = read_text(path)
    source = re.sub(r"```.*?```", " ", source, flags=re.DOTALL)
    source = re.sub(r"`[^`]*`", " ", source)
    source = re.sub(r"https?://\S+", " ", source)
    return source


def validate_british_english(prose_by_path: dict[Path, str]) -> None:
    issues: list[str] = []
    for path, prose in prose_by_path.items():
        for american, british in AMERICAN_TO_BRITISH.items():
            if re.search(rf"\b{re.escape(american)}\b", prose, re.IGNORECASE):
                label = path.relative_to(REPOSITORY_ROOT) if path.is_relative_to(REPOSITORY_ROOT) else path
                issues.append(f"{label}: {american!r} should be {british!r}")
    if issues:
        raise PublicationError("American English spelling detected:\n- " + "\n- ".join(issues))


def privacy_prose(path: Path, source: str) -> str:
    """Return public-facing prose suitable for generic absolute-path checks."""
    if path.name == ".gitignore":
        return ""
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        inventory = PageInventory()
        inventory.feed(source)
        inventory.close()
        return "\n".join(inventory.visible_text)
    if suffix == ".md":
        return markdown_prose(source)
    if suffix in {".py", ".css", ".js"}:
        return ""
    return source


def contains_generic_absolute_path(path: Path, source: str) -> bool:
    prose = NETWORK_URL_IN_PROSE_PATTERN.sub(" ", privacy_prose(path, source))
    # A bare `file://` token appears in offline-opening guidance and has no
    # filesystem target. Keep rejecting file URLs that include a third slash
    # or any following path material.
    prose = re.sub(r"\bfile://(?=\s|$)", " ", prose, flags=re.IGNORECASE)
    return bool(
        POSIX_ABSOLUTE_PATH_IN_PROSE_PATTERN.search(prose)
        or UNC_ABSOLUTE_PATH_IN_PROSE_PATTERN.search(prose)
        or HOME_DIRECTORY_PATH_IN_PROSE_PATTERN.search(prose)
    )


def validate_privacy(paths: list[Path]) -> None:
    issues: list[str] = []
    for path in paths:
        relative = path.relative_to(REPOSITORY_ROOT)
        if ".superpowers" in relative.parts:
            issues.append(f"{relative}: private planning artefact is tracked")
            continue
        name = relative.name.lower()
        is_approval = relative.suffix.lower() == ".json" and "approval" in name
        is_sanitised_example = relative.parts[:3] == (
            "research-briefing-dashboard",
            "examples",
            "folder-mode",
        )
        if is_approval or ".research-briefing-work" in relative.parts:
            issues.append(f"{relative}: private Folder Mode run artefact is public")
            continue
        if name in FOLDER_MODE_ARTEFACT_NAMES and not is_sanitised_example:
            issues.append(f"{relative}: unexpected Folder Mode run artefact is public")
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if not path.is_file() or (
            path.suffix.lower() not in TEXT_SUFFIXES and path.name not in PUBLIC_TEXT_NAMES
        ):
            continue
        source = read_text(path)
        for label, pattern in PRIVACY_PATTERNS.items():
            if pattern.search(source):
                issues.append(f"{relative}: contains {label}")
        if contains_generic_absolute_path(path, source):
            issues.append(f"{relative}: contains an absolute local path")
    if issues:
        raise PublicationError("Privacy boundary failed:\n- " + "\n- ".join(issues))


def validate_skill_metadata() -> None:
    skill_root = REPOSITORY_ROOT / "research-briefing-dashboard"
    skill_path = skill_root / "SKILL.md"
    skill_source = read_text(skill_path)
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", skill_source, re.DOTALL)
    if frontmatter is None:
        raise PublicationError("research-briefing-dashboard/SKILL.md: invalid frontmatter")
    fields = re.findall(r"^([a-z_]+):\s*(.+)$", frontmatter.group(1), re.MULTILINE)
    if {key for key, _ in fields} != {"name", "description"} or len(fields) != 2:
        raise PublicationError(
            "research-briefing-dashboard/SKILL.md: frontmatter must contain only name and description"
        )
    description = dict(fields)["description"]
    if not description.startswith("Use when"):
        raise PublicationError(
            "research-briefing-dashboard/SKILL.md: description must start with 'Use when'"
        )
    if (skill_root / "README.md").exists():
        raise PublicationError("research-briefing-dashboard: Skill-folder README is forbidden")

    agents_path = skill_root / "agents" / "openai.yaml"
    agents_source = read_text(agents_path)
    values: dict[str, str] = {}
    for key in ("display_name", "short_description", "default_prompt"):
        match = re.search(rf'^  {key}: "([^"\n]*)"$', agents_source, re.MULTILINE)
        if match is None:
            raise PublicationError(
                f"research-briefing-dashboard/agents/openai.yaml: {key} must be a quoted string"
            )
        values[key] = match.group(1)
    length = len(values["short_description"])
    if not 25 <= length <= 64:
        raise PublicationError(
            "research-briefing-dashboard/agents/openai.yaml: short_description must contain 25 to 64 characters"
        )
    if "$research-briefing-dashboard" not in values["default_prompt"]:
        raise PublicationError(
            "research-briefing-dashboard/agents/openai.yaml: default_prompt must name $research-briefing-dashboard"
        )


def expected_archive_members() -> dict[str, Path]:
    """Map explicit allow-listed Skill members to their current source files."""
    try:
        sources = load_packager().source_files()
    except (OSError, ValueError) as exc:
        raise PublicationError(f"Skill package allow-list failed: {exc}") from exc
    return {
        source.relative_to(REPOSITORY_ROOT).as_posix(): source
        for source in sources
    }


def validate_release_consistency() -> None:
    """Require the public site, release notes and package to agree on v1.2."""
    readme = read_text(REPOSITORY_ROOT / "README.md")
    index = read_text(REPOSITORY_ROOT / "index.html")
    changelog_path = REPOSITORY_ROOT / "CHANGELOG.md"
    changelog = read_text(changelog_path)
    issues: list[str] = []
    website_pattern = (
        rf"\bVersion\s+{re.escape(TARGET_WEBSITE_VERSION)}(?:\.0)?\b"
    )
    if not re.search(website_pattern, readme):
        issues.append(
            f"README.md does not identify Version {TARGET_WEBSITE_VERSION}"
        )
    if not re.search(website_pattern, index):
        issues.append(
            f"index.html does not identify Version {TARGET_WEBSITE_VERSION}"
        )
    release_pattern = rf"^##\s+\[?{re.escape(TARGET_RELEASE)}\]?(?:\s|$)"
    if not re.search(release_pattern, changelog, re.MULTILINE):
        issues.append(
            f"CHANGELOG.md does not contain a {TARGET_RELEASE} release heading"
        )

    try:
        packaged = {
            source.relative_to(
                REPOSITORY_ROOT / "research-briefing-dashboard"
            ).as_posix()
            for source in load_packager().source_files()
        }
    except (OSError, ValueError) as exc:
        issues.append(f"package allow-list could not be checked: {exc}")
    else:
        missing = sorted(REQUIRED_V12_PACKAGE_MEMBERS - packaged)
        if missing:
            issues.append(
                "v1.2 package member(s) are absent: " + ", ".join(missing)
            )

    if issues:
        raise PublicationError("Release consistency failed:\n- " + "\n- ".join(issues))


def markdown_prose(source: str) -> str:
    """Remove code and link destinations before spelling checks."""
    source = re.sub(r"```.*?```", " ", source, flags=re.DOTALL)
    source = re.sub(r"`[^`]*`", " ", source)
    source = re.sub(r"https?://\S+", " ", source)
    return source


def validate_archive(path: Path) -> int:
    if not path.exists():
        raise PublicationError(f"{path.name}: archive is missing")
    expected = expected_archive_members()
    packager = load_packager()
    issues: list[str] = []
    archive_prose: dict[Path, str] = {}
    with zipfile.ZipFile(path) as archive:
        if archive.comment:
            issues.append("contains an archive comment")
        bad_member = archive.testzip()
        if bad_member:
            issues.append(f"CRC failure in {bad_member}")
        ordered_names = archive.namelist()
        names = set(ordered_names)
        if len(ordered_names) != len(names):
            issues.append("contains duplicate member names")
        if ordered_names != list(expected):
            issues.append(
                "member order does not match the canonical package allow-list"
            )
        missing = sorted(set(expected) - names)
        unexpected = sorted(names - set(expected))
        if missing:
            issues.append("missing current source member(s): " + ", ".join(missing))
        if unexpected:
            issues.append("unexpected member(s): " + ", ".join(unexpected))

        for name in ordered_names:
            information = archive.getinfo(name)
            member = Path(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name:
                issues.append(f"unsafe member path {name!r}")
            if any(part in FORBIDDEN_ARCHIVE_PARTS for part in member.parts):
                issues.append(f"forbidden member {name!r}")
            if member.name.endswith((".pyc", ".pyo")):
                issues.append(f"cache member {name!r}")
            lowered = member.name.lower()
            if "meeting-state" in lowered and lowered.endswith(".json"):
                issues.append(f"exported meeting state {name!r}")
            if information.date_time != packager.ARCHIVE_TIMESTAMP:
                issues.append(f"non-canonical timestamp for {name!r}")
            if information.create_system != 3:
                issues.append(f"non-canonical creator system for {name!r}")
            if information.external_attr != 0o100644 << 16:
                issues.append(f"non-canonical file mode for {name!r}")
            if information.compress_type != zipfile.ZIP_DEFLATED:
                issues.append(f"non-canonical compression for {name!r}")
            if information.comment:
                issues.append(f"contains a member comment for {name!r}")
            if information.extra:
                issues.append(f"contains unexpected extra metadata for {name!r}")

            data = archive.read(name)
            source_path = expected.get(name)
            if source_path is not None and data != source_path.read_bytes():
                issues.append(f"stale or modified member {name!r}")
            if member.suffix.lower() not in TEXT_SUFFIXES and member.name not in PUBLIC_TEXT_NAMES:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(f"text member is not valid UTF-8: {name!r}")
                continue
            for label, pattern in PRIVACY_PATTERNS.items():
                if pattern.search(text):
                    issues.append(f"{name!r} contains {label}")
            if contains_generic_absolute_path(member, text):
                issues.append(f"{name!r} contains an absolute local path")

            if member.suffix.lower() in {".html", ".htm"}:
                inventory = PageInventory()
                inventory.feed(text)
                inventory.close()
                issues.extend(
                    f"{name!r} {issue}"
                    for issue in runtime_dependency_issues(text, inventory)
                )
                is_template = name.endswith("/assets/briefing_template.html")
                if not is_template and re.search(r"\{\{[^{}]+\}\}", text):
                    issues.append(f"{name!r} contains an unresolved template token")
                prose = "\n".join(inventory.visible_text)
            elif member.suffix.lower() == ".md":
                prose = markdown_prose(text)
            else:
                prose = text
            archive_prose[source_path or Path(name)] = prose.replace(
                "scroll-behavior",
                "",
            )

    if issues:
        raise PublicationError(f"{path.name}: " + "; ".join(sorted(set(issues))))
    validate_british_english(archive_prose)
    return len(names)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "generated_html",
        nargs="*",
        type=Path,
        help="Additional generated HTML files to validate",
    )
    arguments = parser.parse_args(argv[1:])

    try:
        pages = [
            *published_html_files(),
            *(path.resolve() for path in arguments.generated_html),
        ]
        markdown_files = publication_markdown_files()
        prose_by_path: dict[Path, str] = {}
        for path in pages:
            inventory = validate_html(path)
            prose_by_path[path] = "\n".join(inventory.visible_text)
        for path in markdown_files:
            validate_markdown_links(path)
            prose_by_path[path] = prose_from_markdown(path)
        agents_yaml = REPOSITORY_ROOT / "research-briefing-dashboard" / "agents" / "openai.yaml"
        prose_by_path[agents_yaml] = read_text(agents_yaml)
        validate_british_english(prose_by_path)
        inventory = public_inventory()
        validate_privacy(inventory)
        validate_skill_metadata()
        validate_release_consistency()
        archive_members = validate_archive(
            REPOSITORY_ROOT / "Supervisor_Meeting_HTML_Skill.zip"
        )
    except (PublicationError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Publication validation passed: "
        f"{len(pages)} HTML files, {len(markdown_files)} Markdown files, "
        f"{len(inventory)} public paths, {archive_members} ZIP members."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
