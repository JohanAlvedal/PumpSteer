"""Shared pytest fixtures for PumpSteer tests."""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def enable_event_loop_debug():
    """Provide a synchronous event loop fixture for Home Assistant test plugins."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    yield
