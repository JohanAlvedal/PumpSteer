"""Regression tests for source and release version consistency."""

import json
from pathlib import Path

import pytest

from scripts.check_version import (
    CHANGELOG_PATH,
    HACS_JSON_PATH,
    INTEGRATION_DIR,
    MANIFEST_PATH,
    SETTINGS_PATH,
    validate_changelog,
    validate_hacs_json,
    validate_manifest_domain,
    validate_repository,
    validate_versions,
)


@pytest.fixture
def version_files(tmp_path: Path) -> tuple[Path, Path]:
    manifest = tmp_path / "manifest.json"
    settings = tmp_path / "settings.py"
    manifest.write_text(json.dumps({"version": "2.2.4"}), encoding="utf-8")
    settings.write_text('PUMPSTEER_VERSION: Final[str] = "2.2.4"\n', encoding="utf-8")
    return manifest, settings


def test_repository_versions_are_consistent():
    assert validate_versions(MANIFEST_PATH, SETTINGS_PATH)


def test_matching_release_tag_is_accepted(version_files):
    manifest, settings = version_files
    assert validate_versions(manifest, settings, tag="v2.2.4") == "2.2.4"


def test_mismatched_source_versions_are_rejected(version_files):
    manifest, settings = version_files
    settings.write_text('PUMPSTEER_VERSION: Final[str] = "2.2.5"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Version mismatch"):
        validate_versions(manifest, settings)


@pytest.mark.parametrize("tag", ["v2.2.5", "2.2.4", "v"])
def test_invalid_or_mismatched_release_tags_are_rejected(version_files, tag):
    manifest, settings = version_files
    with pytest.raises(ValueError, match="Release tag"):
        validate_versions(manifest, settings, tag=tag)


def test_missing_version_constant_is_rejected(version_files):
    manifest, settings = version_files
    settings.write_text("PID_KP = 2.4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="PUMPSTEER_VERSION not found"):
        validate_versions(manifest, settings)


# --- CHANGELOG -------------------------------------------------------------


CHANGELOG_OK = """# Changelog

## [Unreleased]

## [2.2.5] - Latest

## [2.2.4] - Previous

## [2.2.2-thermal.1] - Pre-release

## [2.0.x] - Summary

## [2.0.0] - Rewrite

## [1.x] - Legacy
"""


def test_repository_changelog_matches_manifest():
    validate_changelog(CHANGELOG_PATH, validate_versions(MANIFEST_PATH, SETTINGS_PATH))


def test_repository_passes_all_checks():
    assert validate_repository()


def test_changelog_with_current_version_first_is_accepted(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG_OK, encoding="utf-8")
    validate_changelog(changelog, "2.2.5")


def test_version_bump_without_changelog_entry_is_rejected(tmp_path):
    """The 2.2.5 case: manifest bumped, changelog still on the previous version."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG_OK, encoding="utf-8")
    with pytest.raises(ValueError, match="Newest CHANGELOG.md entry is '2.2.5'"):
        validate_changelog(changelog, "2.2.6")


def test_duplicate_changelog_entry_is_rejected(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG_OK + "\n## [2.2.4] - Again\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        validate_changelog(changelog, "2.2.5")


def test_misordered_changelog_is_rejected(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [2.2.5] - a\n\n## [2.2.3] - b\n\n## [2.2.4] - c\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="newest first"):
        validate_changelog(changelog, "2.2.5")


def test_invalid_changelog_heading_is_rejected(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [2.2.5] - a\n\n## [v2.2.4] - b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid version headings"):
        validate_changelog(changelog, "2.2.5")


# --- manifest.json ---------------------------------------------------------


@pytest.mark.parametrize("version", ["v2.2.4", "2.2", "2.2.4 ", "2.2.4-"])
def test_malformed_manifest_version_is_rejected(version_files, version):
    manifest, settings = version_files
    manifest.write_text(json.dumps({"version": version}), encoding="utf-8")
    with pytest.raises(ValueError, match="not X.Y.Z"):
        validate_versions(manifest, settings)


def test_prerelease_manifest_version_is_accepted(tmp_path):
    folder = tmp_path / "pumpsteer"
    folder.mkdir()
    manifest = folder / "manifest.json"
    settings = folder / "settings.py"
    manifest.write_text(
        json.dumps({"domain": "pumpsteer", "version": "2.3.0-beta.1"}),
        encoding="utf-8",
    )
    settings.write_text('PUMPSTEER_VERSION = "2.3.0-beta.1"\n', encoding="utf-8")
    assert validate_versions(manifest, settings, tag="v2.3.0-beta.1") == "2.3.0-beta.1"


def test_manifest_domain_must_match_folder(tmp_path):
    folder = tmp_path / "pumpsteer"
    folder.mkdir()
    manifest = folder / "manifest.json"
    manifest.write_text(
        json.dumps({"domain": "pump_steer", "version": "2.2.5"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="domain"):
        validate_manifest_domain(manifest)


# --- hacs.json -------------------------------------------------------------


def test_repository_hacs_json_is_valid():
    validate_hacs_json(HACS_JSON_PATH, INTEGRATION_DIR)


def _write_hacs(tmp_path, data):
    hacs = tmp_path / "hacs.json"
    hacs.write_text(json.dumps(data), encoding="utf-8")
    integration = tmp_path / "custom_components" / "pumpsteer"
    integration.mkdir(parents=True)
    return hacs, integration


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"homeassistant": "2024.4.0"}, "non-empty name"),
        ({"name": "PumpSteer", "domains": ["pumpsteer"]}, "unknown keys"),
        ({"name": "PumpSteer", "homeassistant": "2024.4"}, "homeassistant"),
        ({"name": "PumpSteer", "homeassistant": 2024}, "homeassistant"),
    ],
)
def test_invalid_hacs_json_is_rejected(tmp_path, data, match):
    hacs, integration = _write_hacs(tmp_path, data)
    with pytest.raises(ValueError, match=match):
        validate_hacs_json(hacs, integration)


def test_beta_minimum_ha_version_is_accepted(tmp_path):
    hacs, integration = _write_hacs(
        tmp_path, {"name": "PumpSteer", "homeassistant": "2026.11.0b0"}
    )
    validate_hacs_json(hacs, integration)


def test_duplicate_hacs_json_in_integration_is_rejected(tmp_path):
    hacs, integration = _write_hacs(tmp_path, {"name": "PumpSteer"})
    (integration / "hacs.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="only exist in the repository root"):
        validate_hacs_json(hacs, integration)
