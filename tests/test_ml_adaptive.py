import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

from custom_components.pumpsteer.ml_adaptive import PumpSteerMLCollector


class DummyHass:
    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_task(self, coro):
        return asyncio.create_task(coro)


def test_end_session_without_target_temp_marks_failure():
    async def run_test():
        hass = DummyHass()
        collector = PumpSteerMLCollector(hass)

        async def async_noop():
            return None

        collector.async_update_learning_model = async_noop
        collector.async_save_data = async_noop

        collector.start_session({"mode": "heating"})
        collector.update_session(
            {
                "indoor_temp": 20.0,
                "outdoor_temp": 5.0,
                "target_temp": None,
            }
        )
        collector.end_session("normal")
        await asyncio.sleep(0)

        summary = collector.learning_sessions[-1]["summary"]
        assert summary["comfort_drift"] is None
        assert summary["success"] is False

    asyncio.run(run_test())
