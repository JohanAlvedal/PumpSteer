"""Structured runtime file logging for PumpSteer."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .settings import PUMP_LOG_ENABLED

LOG_DIR_NAME = "pumplog"
PUMP_LOG_FILE = "pump.log"
TELEMETRY_FILE = "telemetry.json"
LOGGING_OUTDOOR_TEMP_THRESHOLD_C = 10.0
_MAX_BYTES = 1_000_000

_runtime_log_dir = Path("/config") / LOG_DIR_NAME
_pump_log_path = _runtime_log_dir / PUMP_LOG_FILE
_telemetry_path = _runtime_log_dir / TELEMETRY_FILE

_file_logger = logging.getLogger("pumpsteer.pump_log")
_file_logger.propagate = False


def _coerce_outdoor_temp(outdoor_temp: Any) -> Optional[float]:
    """Return outdoor temperature as float, or None when it cannot be trusted."""
    if outdoor_temp is None:
        return None
    if isinstance(outdoor_temp, str):
        stripped = outdoor_temp.strip().lower()
        if stripped in {"", "unknown", "unavailable", "none"}:
            return None
        outdoor_temp = stripped
    try:
        return float(outdoor_temp)
    except (TypeError, ValueError):
        return None


def _should_write_runtime_logs(outdoor_temp: Any) -> bool:
    """Return True when runtime logs are useful enough to write."""
    parsed_outdoor_temp = _coerce_outdoor_temp(outdoor_temp)
    if parsed_outdoor_temp is None:
        # Missing or invalid outdoor temperature means heating relevance cannot be
        # assessed safely, so skip disk writes to avoid unnecessary I/O.
        return False
    return parsed_outdoor_temp <= LOGGING_OUTDOOR_TEMP_THRESHOLD_C


def _resolve_log_dir(hass: Any | None = None) -> Path:
    """Resolve the Home Assistant writable runtime log directory."""
    if hass is not None and hasattr(hass, "config") and hasattr(hass.config, "path"):
        return Path(hass.config.path(LOG_DIR_NAME))
    return Path("/config") / LOG_DIR_NAME


def setup_pump_log(hass: Any | None = None) -> None:
    """Initialize the file handler. Should be called via executor, not the event loop."""
    global _runtime_log_dir, _pump_log_path, _telemetry_path

    _runtime_log_dir = _resolve_log_dir(hass)
    _pump_log_path = _runtime_log_dir / PUMP_LOG_FILE
    _telemetry_path = _runtime_log_dir / TELEMETRY_FILE
    _runtime_log_dir.mkdir(parents=True, exist_ok=True)

    if _file_logger.handlers:
        for handler in _file_logger.handlers:
            if (
                isinstance(handler, logging.FileHandler)
                and Path(handler.baseFilename) == _pump_log_path
            ):
                return
            handler.close()
        _file_logger.handlers.clear()

    try:
        if _pump_log_path.exists() and _pump_log_path.stat().st_size > _MAX_BYTES:
            rotated = _pump_log_path.with_name(f"{PUMP_LOG_FILE}.1")
            if rotated.exists():
                rotated.unlink()
            _pump_log_path.rename(rotated)
        handler = logging.FileHandler(_pump_log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        _file_logger.addHandler(handler)
        _file_logger.setLevel(logging.DEBUG)
    except OSError:
        pass


def log_mode_change(
    old_mode: Optional[str],
    new_mode: str,
    fake_temp: float,
    indoor: Optional[float],
    outdoor: Optional[float],
    price_cat: Optional[str],
    p30: Optional[float],
    p80: Optional[float],
    brake_factor: Optional[float] = None,
    ramp_in: Optional[float] = None,
    comfort_floor: Optional[float] = None,
    extra: Optional[str] = None,
) -> None:
    if not PUMP_LOG_ENABLED:
        return
    if old_mode == new_mode:
        return
    if not _should_write_runtime_logs(outdoor):
        return
    if not _file_logger.handlers:
        return
    parts = [f"MODE {old_mode or '?'} → {new_mode}", f"fake={fake_temp:.1f}°C"]
    if indoor is not None:
        parts.append(f"indoor={indoor:.1f}°C")
    if outdoor is not None:
        parts.append(f"outdoor={outdoor:.1f}°C")
    if price_cat:
        parts.append(f"price_cat={price_cat}")
    if p30 is not None and p80 is not None:
        parts.append(f"p30={p30:.4f} p80={p80:.4f}")
    if brake_factor is not None:
        parts.append(f"brake_factor={brake_factor:.2f}")
    if ramp_in is not None:
        parts.append(f"ramp_in={ramp_in:.0f}min")
    if comfort_floor is not None:
        parts.append(f"comfort_floor={comfort_floor:.1f}°C")
    if extra:
        parts.append(extra)
    _file_logger.info("  |  ".join(parts))


def log_event(msg: str, **kwargs: Any) -> None:
    if not PUMP_LOG_ENABLED:
        return
    outdoor = kwargs.get("outdoor", kwargs.get("outdoor_temperature"))
    if not _should_write_runtime_logs(outdoor):
        return
    if not _file_logger.handlers:
        return
    if kwargs:
        kv = "  ".join(f"{k}={v}" for k, v in kwargs.items())
        _file_logger.info(f"{msg}  |  {kv}")
    else:
        _file_logger.info(msg)


def write_telemetry(data: dict[str, Any], outdoor_temp: Any) -> None:
    """Write the latest runtime telemetry snapshot when heating control is relevant."""
    if not _should_write_runtime_logs(outdoor_temp):
        return
    try:
        _runtime_log_dir.mkdir(parents=True, exist_ok=True)
        with _telemetry_path.open("w", encoding="utf-8") as telemetry_file:
            json.dump(
                data, telemetry_file, ensure_ascii=False, indent=2, sort_keys=True
            )
            telemetry_file.write("\n")
    except OSError:
        pass
