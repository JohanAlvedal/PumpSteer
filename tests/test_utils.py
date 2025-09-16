import builtins
import json
from pathlib import Path
from custom_components.pumpsteer.utils import get_version


def test_get_version_reads_manifest():
    manifest_path = Path("custom_components/pumpsteer/manifest.json")
    with open(manifest_path) as f:
        version = json.load(f)["version"]
    assert get_version() == version


def test_get_version_missing_manifest(monkeypatch):
    def fake_open(*args, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(builtins, "open", fake_open)
    assert get_version() == "unknown"
