import json
from pathlib import Path

from custom_components.pumpsteer import pump_log


class DummyConfig:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, *parts: str) -> str:
        return str(self.root.joinpath(*parts))


class DummyHass:
    def __init__(self, root: Path) -> None:
        self.config = DummyConfig(root)


def teardown_function() -> None:
    for handler in list(pump_log._file_logger.handlers):
        handler.close()
        pump_log._file_logger.removeHandler(handler)


def test_setup_pump_log_uses_pumplog_directory_and_creates_it_without_files(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    log_dir = tmp_path / pump_log.LOG_DIR_NAME
    assert log_dir.is_dir()
    assert pump_log.LOG_DIR_NAME == "pumplog"
    assert not (log_dir / "pump.log").exists()
    assert not (log_dir / "telemetry.json").exists()


def test_pump_log_written_when_real_outdoor_temperature_is_10(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    pump_log.log_mode_change(None, "normal", 7.0, 20.0, 10.0, "normal", 1.0, 2.0)
    for handler in pump_log._file_logger.handlers:
        handler.flush()

    log_path = tmp_path / "pumplog" / "pump.log"
    assert log_path.exists()
    assert "MODE ? → normal" in log_path.read_text(encoding="utf-8")


def test_telemetry_written_when_real_outdoor_temperature_is_below_10(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    pump_log.write_telemetry({"mode": "normal"}, 9.9)

    telemetry_path = tmp_path / "pumplog" / "telemetry.json"
    assert telemetry_path.exists()
    assert json.loads(telemetry_path.read_text(encoding="utf-8")) == {"mode": "normal"}


def test_runtime_files_not_created_when_real_outdoor_temperature_is_11(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    pump_log.log_mode_change(None, "normal", 7.0, 20.0, 11.0, "normal", 1.0, 2.0)
    pump_log.write_telemetry({"mode": "normal"}, 11.0)

    assert not (tmp_path / "pumplog" / "pump.log").exists()
    assert not (tmp_path / "pumplog" / "telemetry.json").exists()


def test_runtime_files_not_updated_when_real_outdoor_temperature_is_warm(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))
    log_path = tmp_path / "pumplog" / "pump.log"
    telemetry_path = tmp_path / "pumplog" / "telemetry.json"
    log_path.write_text("existing\n", encoding="utf-8")
    telemetry_path.write_text('{"old": true}\n', encoding="utf-8")
    log_mtime = log_path.stat().st_mtime_ns
    telemetry_mtime = telemetry_path.stat().st_mtime_ns

    pump_log.log_mode_change(None, "normal", 7.0, 20.0, 10.1, "normal", 1.0, 2.0)
    pump_log.write_telemetry({"mode": "normal"}, 10.1)
    for handler in pump_log._file_logger.handlers:
        handler.flush()

    assert log_path.read_text(encoding="utf-8") == "existing\n"
    assert telemetry_path.read_text(encoding="utf-8") == '{"old": true}\n'
    assert log_path.stat().st_mtime_ns == log_mtime
    assert telemetry_path.stat().st_mtime_ns == telemetry_mtime


def test_fake_output_temperature_below_10_does_not_write_when_real_outdoor_is_warm(
    tmp_path,
):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    fake_output_temp = 5.0
    real_outdoor_temp = 11.0
    pump_log.log_mode_change(
        None, "normal", fake_output_temp, 20.0, real_outdoor_temp, "normal", 1.0, 2.0
    )
    pump_log.write_telemetry(
        {"fake_outdoor_temperature": fake_output_temp}, real_outdoor_temp
    )

    assert not (tmp_path / "pumplog" / "pump.log").exists()
    assert not (tmp_path / "pumplog" / "telemetry.json").exists()


def test_invalid_outdoor_temperatures_do_not_crash_or_write(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))
    log_path = tmp_path / "pumplog" / "pump.log"

    for invalid in ("unknown", "unavailable", None, "not-a-number"):
        pump_log.log_event("EVENT", outdoor=invalid)
        pump_log.write_telemetry({"invalid": invalid}, invalid)

    for handler in pump_log._file_logger.handlers:
        handler.flush()

    assert not log_path.exists()
    assert not (tmp_path / "pumplog" / "telemetry.json").exists()


def test_set_state_uses_real_outdoor_temperature_for_runtime_log_gate(monkeypatch):
    import asyncio
    from datetime import datetime, timezone

    from custom_components.pumpsteer import sensor as sensor_module
    from custom_components.pumpsteer.sensor import PumpSteerSensor

    class DummyEntry:
        entry_id = "entry"
        data = {}
        options = {}

        def add_update_listener(self, listener):
            return None

    captured = {}

    def fake_log_mode_change(**kwargs):
        captured["log_outdoor"] = kwargs["outdoor"]
        captured["fake_temp"] = kwargs["fake_temp"]

    def fake_write_telemetry(data, outdoor_temp):
        captured["telemetry_outdoor"] = outdoor_temp
        captured["telemetry_fake"] = data["fake_outdoor_temperature"]

    async def fake_async_push_ohmigo(hass, config_entry, fake_temp, last_push):
        return last_push

    monkeypatch.setattr(sensor_module, "log_mode_change", fake_log_mode_change)
    monkeypatch.setattr(sensor_module, "write_telemetry", fake_write_telemetry)
    monkeypatch.setattr(sensor_module, "async_push_ohmigo", fake_async_push_ohmigo)

    pump_sensor = PumpSteerSensor(DummyHass(Path("/tmp")), DummyEntry())
    asyncio.run(
        pump_sensor._set_state(
            5.0,
            "normal",
            {"outdoor_temperature": 11.0, "indoor_temperature": 20.0},
            datetime.now(timezone.utc),
        )
    )

    assert captured == {
        "log_outdoor": 11.0,
        "fake_temp": 5.0,
        "telemetry_outdoor": 11.0,
        "telemetry_fake": 5.0,
    }
