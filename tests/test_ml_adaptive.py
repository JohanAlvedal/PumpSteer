import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401 - sets up Home Assistant stubs

from custom_components.pumpsteer.ml_adaptive import (
    PumpSteerMLCollector,
    LearningSession,
)


class DummyLoop:
    def create_task(self, coro):
        import asyncio

        asyncio.get_event_loop().run_until_complete(coro)


class DummyHass:
    def __init__(self):
        self.states = {}
        self.services = type("Services", (), {"call": lambda *args, **kwargs: None})()
        self.loop = DummyLoop()

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def test_session_lifecycle(tmp_path):
    hass = DummyHass()
    data_file = tmp_path / "ml_data.json"
    collector = PumpSteerMLCollector(hass, data_file_path=str(data_file))

    collector.start_session(
        {
            "mode": "heating",
            "aggressiveness": 3,
            "inertia": 2.0,
            "indoor_temp": 20.0,
            "target_temp": 21.0,
        }
    )

    assert isinstance(collector.current_session, LearningSession)

    collector.update_session({"indoor_temp": 20.5, "target_temp": 21.0})
    collector.end_session("normal", {"indoor_temp": 21.0})

    assert collector.current_session is None
    assert len(collector.learning_sessions) == 1
    session = collector.learning_sessions[0]
    assert "summary" in session and session["summary"]["mode"] == "heating"
