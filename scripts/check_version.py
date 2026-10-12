"""Check that PumpSteer integration versions agree before a release."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "pumpsteer" / "manifest.json"
SETTINGS_PATH = ROOT / "custom_components" / "pumpsteer" / "settings.py"


def _settings_version(path: Path) -> str:
    """Read the version constant without importing Home Assistant."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        value = None
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "PUMPSTEER_VERSION":
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


def main() -> int:
    """Run source checks locally or validate a GitHub release tag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag", help="Release tag to check against the integration (e.g. v2.2.3)"
    )
    args = parser.parse_args()

    try:
        version = validate_versions(tag=args.tag)
    except (OSError, ValueError, SyntaxError) as err:
        print(f"PumpSteer version validation failed: {err}", file=sys.stderr)
        return 1

    print(f"PumpSteer version validation passed: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
