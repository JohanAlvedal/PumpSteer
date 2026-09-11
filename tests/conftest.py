import sys
from pathlib import Path

# Add the project root (/config).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Add the pumpsteer package directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load Home Assistant stubs before importing integration modules.
import ha_test_stubs  # noqa: F401, E402
