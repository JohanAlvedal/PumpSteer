import asyncio
import sys
from pathlib import Path

# Add the project root (/config).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Add the pumpsteer package directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _AutoCreatingEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Restore implicit loop creation expected by the HA pytest plugin."""

    def get_event_loop(self):
        try:
            return super().get_event_loop()
        except RuntimeError:
            loop = self.new_event_loop()
            self.set_event_loop(loop)
            return loop


# Python 3.13+ no longer creates a default event loop implicitly. The Home
# Assistant pytest plugin still calls get_event_loop() during fixture setup.
if sys.version_info >= (3, 13):
    asyncio.set_event_loop_policy(_AutoCreatingEventLoopPolicy())

# Load Home Assistant stubs before importing integration modules.
import ha_test_stubs  # noqa: F401, E402
