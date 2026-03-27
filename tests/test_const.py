from custom_components.pumpsteer.sensor import PumpSteerSensor


class DummyHass:
    pass


class DummyConfigEntry:
    entry_id = "test"

    def add_update_listener(self, listener):
        return None


def test_extra_state_attributes_basic():
    s = PumpSteerSensor(DummyHass(), DummyConfigEntry())
    s._state = 5.0
    s._attributes = {
        "mode": "heating",
        "current_price": 1.2,
        "aggressiveness": 3,
    }

    attrs = s.extra_state_attributes

    assert attrs["mode"] == "heating"
    assert attrs["current_price"] == 1.2
    assert attrs["aggressiveness"] == 3
    assert attrs["friendly_name"] == "PumpSteer"