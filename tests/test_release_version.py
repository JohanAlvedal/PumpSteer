"""Regression tests for source and release version consistency."""

import json
from pathlib import Path

import pytest

from scripts.check_version import MANIFEST_PATH, SETTINGS_PATH, validate_versions


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
