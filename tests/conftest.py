"""Pytest configuration for Home Assistant stubs."""

from pathlib import Path
import sys

import ha_test_stubs  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
