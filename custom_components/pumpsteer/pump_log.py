"""Structured file logger for PumpSteer — writes to /config/pump.log."""

from __future__ import annotations

import logging
import os
import json
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

from .settings import PUMP_LOG_ENABLED

_PUMP_LOG_PATH = "/config/pump.log"
_MAX_BYTES = 1_000_000
_TELEMETRY_DIR = "/config/pumpsteer"
_TELEMETRY_PATH = f"{_TELEMETRY_DIR}/telemetry.jsonl"
_TELEMETRY_MAX_BYTES = 5 * 1024 * 1024
_TELEMETRY_BACKUP_COUNT = 3

_file_logger = logging.getLogger("pumpsteer.pump_log")
_file_logger.propagate = False
_telemetry_logger = logging.getLogger("pumpsteer.telemetry")
_telemetry_logger.propagate = False


def setup_pump_log() -> None:
    """Initiera fil-handler. Ska anropas via executor, inte från event loop."""
    if _file_logger.handlers and _telemetry_logger.handlers:
        return
    try:
        if not _file_logger.handlers:
            if (
                os.path.exists(_PUMP_LOG_PATH)
                and os.path.getsize(_PUMP_LOG_PATH) > _MAX_BYTES
            ):
                rotated = _PUMP_LOG_PATH + ".1"
                if os.path.exists(rotated):
                    os.remove(rotated)
                os.rename(_PUMP_LOG_PATH, rotated)
            handler = logging.FileHandler(_PUMP_LOG_PATH, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            _file_logger.addHandler(handler)
            _file_logger.setLevel(logging.DEBUG)

        if not _telemetry_logger.handlers:
            os.makedirs(_TELEMETRY_DIR, exist_ok=True)
            telemetry_handler = RotatingFileHandler(
                _TELEMETRY_PATH,
                maxBytes=_TELEMETRY_MAX_BYTES,
                backupCount=_TELEMETRY_BACKUP_COUNT,
                encoding="utf-8",
            )
            telemetry_handler.setFormatter(logging.Formatter("%(message)s"))
            _telemetry_logger.addHandler(telemetry_handler)
            _telemetry_logger.setLevel(logging.INFO)
    except OSError:
        pass


def _json_default(value: Any) -> str:
    """Convert non-JSON values to strings."""
    return str(value)


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
    if not _file_logger.handlers:
        return
    if kwargs:
        kv = "  ".join(f"{k}={v}" for k, v in kwargs.items())
        _file_logger.info(f"{msg}  |  {kv}")
    else:
        _file_logger.info(msg)


def log_telemetry_snapshot(**data: Any) -> None:
    """Write one structured telemetry snapshot for later analysis."""
    if not PUMP_LOG_ENABLED:
        return
    if not _telemetry_logger.handlers:
        return

    payload = dict(data)
    payload.setdefault("timestamp", datetime.now().astimezone().isoformat())
    try:
        _telemetry_logger.info(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                default=_json_default,
            )
        )
    except Exception:
        return
