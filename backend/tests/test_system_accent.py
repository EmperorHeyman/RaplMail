"""The Windows accent colour feeding the dynamic (Material You) palette."""

import sys

import pytest

from app.api import settings as settings_api


def test_endpoint_shape(client):
    r = client.get("/settings/system-accent")
    assert r.status_code == 200
    color = r.json()["color"]
    assert color is None or (color.startswith("#") and len(color) == 7)


@pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows registry")
def test_abgr_dword_is_decoded(monkeypatch):
    import winreg

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # 0xAABBGGRR: Windows' default blue #0078d4 is stored as 0xffd47800.
    monkeypatch.setattr(winreg, "OpenKey", lambda *a: Key())
    monkeypatch.setattr(winreg, "QueryValueEx", lambda key, name: (0xFFD47800, winreg.REG_DWORD))
    assert settings_api.windows_accent() == "#0078d4"


@pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows registry")
def test_missing_values_give_none(monkeypatch):
    import winreg

    def boom(*a):
        raise OSError("no such key")

    monkeypatch.setattr(winreg, "OpenKey", boom)
    assert settings_api.windows_accent() is None


def test_off_windows_is_none(monkeypatch):
    monkeypatch.setattr(settings_api.sys, "platform", "linux")
    assert settings_api.windows_accent() is None
