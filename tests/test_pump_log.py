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


def test_setup_pump_log_uses_pumplog_directory_and_creates_it(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    assert (tmp_path / pump_log.LOG_DIR_NAME).is_dir()
    assert pump_log.LOG_DIR_NAME == "pumplog"


def test_pump_log_written_when_outdoor_temperature_is_cold(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    pump_log.log_mode_change(None, "normal", 7.0, 20.0, 10.0, "normal", 1.0, 2.0)
    for handler in pump_log._file_logger.handlers:
        handler.flush()

    log_path = tmp_path / "pumplog" / "pump.log"
    assert log_path.exists()
    assert "MODE ? → normal" in log_path.read_text(encoding="utf-8")


def test_telemetry_written_when_outdoor_temperature_is_cold(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))

    pump_log.write_telemetry({"mode": "normal"}, 9.9)

    telemetry_path = tmp_path / "pumplog" / "telemetry.json"
    assert telemetry_path.exists()
    assert json.loads(telemetry_path.read_text(encoding="utf-8")) == {"mode": "normal"}


def test_runtime_files_not_updated_when_outdoor_temperature_is_warm(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))
    log_path = tmp_path / "pumplog" / "pump.log"
    telemetry_path = tmp_path / "pumplog" / "telemetry.json"
    log_path.write_text("existing\n", encoding="utf-8")
    telemetry_path.write_text('{"old": true}\n', encoding="utf-8")

    pump_log.log_mode_change(None, "normal", 7.0, 20.0, 10.1, "normal", 1.0, 2.0)
    pump_log.write_telemetry({"mode": "normal"}, 10.1)
    for handler in pump_log._file_logger.handlers:
        handler.flush()

    assert log_path.read_text(encoding="utf-8") == "existing\n"
    assert telemetry_path.read_text(encoding="utf-8") == '{"old": true}\n'


def test_invalid_outdoor_temperatures_do_not_crash_or_write(tmp_path):
    pump_log.setup_pump_log(DummyHass(tmp_path))
    log_path = tmp_path / "pumplog" / "pump.log"

    for invalid in ("unknown", "unavailable", None, "not-a-number"):
        pump_log.log_event("EVENT", outdoor=invalid)
        pump_log.write_telemetry({"invalid": invalid}, invalid)

    for handler in pump_log._file_logger.handlers:
        handler.flush()

    assert log_path.read_text(encoding="utf-8") == ""
    assert not (tmp_path / "pumplog" / "telemetry.json").exists()
