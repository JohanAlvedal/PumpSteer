"""Import checks for the PumpSteer integration."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


MODULES_TO_CHECK = [
    "custom_components.pumpsteer",
    "custom_components.pumpsteer.config_flow",
    "custom_components.pumpsteer.sensor",
    "custom_components.pumpsteer.temp_control_logic",
]


def main() -> None:
    """Import configured modules and fail fast on errors."""
    failures: list[str] = []

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    for module_name in MODULES_TO_CHECK:
        try:
            importlib.import_module(module_name)
        except ImportError as exc:
            failures.append(f"{module_name}: {exc}")

    if failures:
        for failure in failures:
            print(f"Import check failed: {failure}", file=sys.stderr)
        raise SystemExit(1)

    print("Import check passed.")


if __name__ == "__main__":
    main()
