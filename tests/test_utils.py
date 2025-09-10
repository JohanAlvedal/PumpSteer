import builtins
from custom_components.pumpsteer.utils import get_version


def test_get_version_reads_manifest():
    assert get_version() == "1.5.0"


def test_get_version_missing_manifest(monkeypatch):
    def fake_open(*args, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(builtins, "open", fake_open)
    assert get_version() == "unknown"
