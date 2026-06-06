import pytest
from ihonor.config import Config


def test_from_env_raises_when_missing(monkeypatch):
    for k in ("ICLOUD_APPLE_ID", "ICLOUD_PASSWORD", "HONOR_ID", "HONOR_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="ICLOUD_APPLE_ID"):
        Config.from_env()


def test_from_env_loads_all(monkeypatch):
    monkeypatch.setenv("ICLOUD_APPLE_ID", "a@b.com")
    monkeypatch.setenv("ICLOUD_PASSWORD", "pw")
    monkeypatch.setenv("HONOR_ID", "h")
    monkeypatch.setenv("HONOR_PASSWORD", "hp")
    cfg = Config.from_env()
    assert cfg.icloud_apple_id == "a@b.com"
    assert cfg.honor_id == "h"
