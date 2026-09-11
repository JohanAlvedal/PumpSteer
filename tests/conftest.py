import asyncio
import sys
from pathlib import Path

# Add the project root (/config).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Add the pumpsteer package directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Python 3.13+ no longer creates a default event loop implicitly. The
# Home Assistant pytest plugin still expects one during fixture setup.
if sys.version_info >= (3, 13):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

# Load Home Assistant stubs before importing integration modules.
import ha_test_stubs  # noqa: F401, E402
