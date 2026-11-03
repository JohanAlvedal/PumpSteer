"""Check that PumpSteer versions and packaging metadata agree before a release."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "pumpsteer" / "manifest.json"
SETTINGS_PATH = ROOT / "custom_components" / "pumpsteer" / "settings.py"
CHANGELOG_PATH = ROOT / "docs" / "CHANGELOG.md"
HACS_JSON_PATH = ROOT / "hacs.json"
INTEGRATION_DIR = ROOT / "custom_components" / "pumpsteer"

# X.Y.Z with an optional pre-release suffix, e.g. 2.2.5 or 2.2.2-thermal.1
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?$")
# Minimum Home Assistant version in hacs.json, e.g. 2024.4.0 or 2026.11.0b0
HA_VERSION_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d+(?:b\d+)?$")
# Historical summary headings in the changelog, e.g. 2.0.x or 1.x
SUMMARY_HEADING_RE = re.compile(r"^\d+(?:\.\d+)?\.x$")
CHANGELOG_HEADING_RE = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)
# Keys the Marketplace / HACS read from hacs.json
HACS_JSON_KEYS = frozenset(
    {
        "name",
        "content_in_root",
        "filename",
        "zip_release",
        "persistent_directory",
        "homeassistant",
        "hide_default_branch",
        "hacs",
        "country",
    }
)


def _settings_version(path: Path) -> str:
    """Read the version constant without importing Home Assistant."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        value = None
        if isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "PUMPSTEER_VERSION"
            ):
                value = node.value
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "PUMPSTEER_VERSION"
                for target in node.targets
            ):
                value = node.value

        if value is not None:
            if (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.value.strip()
            ):
                return value.value
            raise ValueError("PUMPSTEER_VERSION must be a non-empty string literal")

    raise ValueError("PUMPSTEER_VERSION not found in settings.py")


def validate_versions(
    manifest_path: Path = MANIFEST_PATH,
    settings_path: Path = SETTINGS_PATH,
    tag: str | None = None,
) -> str:
    """Require both source versions and an optional release tag to match."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain an object")

    manifest_version = manifest.get("version")
    if not isinstance(manifest_version, str) or not manifest_version.strip():
        raise ValueError("manifest.json must contain a non-empty version")

    if not VERSION_RE.match(manifest_version):
        raise ValueError(
            f"manifest.json version {manifest_version!r} is not X.Y.Z "
            "(optionally with a -pre.release suffix)"
        )

    settings_version = _settings_version(settings_path)
    if manifest_version != settings_version:
        raise ValueError(
            f"Version mismatch: manifest.json={manifest_version!r}, "
            f"settings.py={settings_version!r}"
        )

    if tag is not None:
        if not tag.startswith("v") or len(tag) < 2:
            raise ValueError(f"Release tag must start with 'v': {tag!r}")
        if tag[1:] != manifest_version:
            raise ValueError(
                f"Release tag {tag!r} does not match integration version "
                f"{manifest_version!r}"
            )

    return manifest_version


def validate_manifest_domain(manifest_path: Path = MANIFEST_PATH) -> None:
    """Require the manifest domain to match the integration folder name."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    domain = manifest.get("domain") if isinstance(manifest, dict) else None
    if domain != manifest_path.parent.name:
        raise ValueError(
            f"manifest.json domain {domain!r} does not match its folder "
            f"{manifest_path.parent.name!r}"
        )


def _version_key(version: str) -> tuple[int, int, int, int, str]:
    """Sort key: release > pre-release of the same X.Y.Z."""
    core, _, pre = version.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    return (major, minor, patch, 0 if pre else 1, pre)


def validate_changelog(changelog_path: Path, version: str) -> None:
    """Require the newest changelog entry to describe the current version."""
    headings = CHANGELOG_HEADING_RE.findall(changelog_path.read_text(encoding="utf-8"))
    entries = [heading for heading in headings if heading != "Unreleased"]
    invalid = [
        heading
        for heading in entries
        if not VERSION_RE.match(heading) and not SUMMARY_HEADING_RE.match(heading)
    ]
    if invalid:
        raise ValueError(f"CHANGELOG.md has invalid version headings: {invalid}")

    released = [heading for heading in entries if VERSION_RE.match(heading)]
    if not released:
        raise ValueError("CHANGELOG.md has no released version entries")

    duplicates = sorted(
        {heading for heading in released if released.count(heading) > 1}
    )
    if duplicates:
        raise ValueError(f"CHANGELOG.md has duplicate entries: {duplicates}")

    if released[0] != version:
        raise ValueError(
            f"Newest CHANGELOG.md entry is {released[0]!r}, but the integration "
            f"version is {version!r}. Add a '## [{version}]' entry."
        )

    if released != sorted(released, key=_version_key, reverse=True):
        raise ValueError("CHANGELOG.md entries are not ordered newest first")


def validate_hacs_json(
    hacs_json_path: Path = HACS_JSON_PATH,
    integration_dir: Path = INTEGRATION_DIR,
) -> None:
    """Require a valid root hacs.json, which the Marketplace needs to install."""
    data = json.loads(hacs_json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("hacs.json must contain an object")  # noqa: TRY004 - main() reports ValueError

    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ValueError("hacs.json must contain a non-empty name")

    unknown = sorted(set(data) - HACS_JSON_KEYS)
    if unknown:
        raise ValueError(f"hacs.json has unknown keys: {unknown}")

    min_ha = data.get("homeassistant")
    if min_ha is not None and (
        not isinstance(min_ha, str) or not HA_VERSION_RE.match(min_ha)
    ):
        raise ValueError(
            f"hacs.json homeassistant {min_ha!r} is not a version like '2024.4.0'"
        )

    if (integration_dir / "hacs.json").exists():
        raise ValueError(
            "hacs.json must only exist in the repository root, "
            f"not in {integration_dir.name}/"
        )


def validate_repository(tag: str | None = None) -> str:
    """Run every version and packaging check on the repository."""
    version = validate_versions(tag=tag)
    validate_manifest_domain()
    validate_changelog(CHANGELOG_PATH, version)
    validate_hacs_json()
    return version


def main() -> int:
    """Run source checks locally or validate a GitHub release tag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag", help="Release tag to check against the integration (e.g. v2.2.3)"
    )
    args = parser.parse_args()

    try:
        version = validate_repository(tag=args.tag)
    except (OSError, ValueError, SyntaxError) as err:
        print(f"PumpSteer version validation failed: {err}", file=sys.stderr)
        return 1

    print(f"PumpSteer version validation passed: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
