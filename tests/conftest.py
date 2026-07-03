import asyncio
import sys

import pytest
from pathlib import Path

# Lägg till projektrot (/config)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Lägg till pumpsteer-mappen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 🔥 VIKTIGAST: ladda stubbar först
import ha_test_stubs  # noqa: F401


@pytest.fixture(autouse=True)
def ensure_event_loop():
    """Ensure sync tests have a current event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            yield
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    else:
        yield
