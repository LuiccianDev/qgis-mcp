import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "qgis_listener"


def _load():
    path = PLUGIN_DIR / "token_store.py"
    spec = importlib.util.spec_from_file_location("qgis_listener_token_store", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.delenv("QGIS_MCP_TOKEN", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return _load()


def test_env_token_wins_over_file(store, monkeypatch):
    store.write_token("from-file")
    monkeypatch.setenv("QGIS_MCP_TOKEN", "from-env")
    assert store.read_token() == "from-env"
    assert store.token_status()["source"] == "env"


def test_reads_file_when_env_unset(store):
    store.write_token("from-file")
    assert store.read_token() == "from-file"
    assert store.token_status()["source"] == "file"


def test_env_whitespace_falls_back_to_file(store, monkeypatch):
    store.write_token("from-file")
    monkeypatch.setenv("QGIS_MCP_TOKEN", "   ")
    assert store.read_token() == "from-file"


def test_whitespace_env_and_empty_file_are_disabled(store, monkeypatch):
    monkeypatch.setenv("QGIS_MCP_TOKEN", "   ")
    assert store.read_token() is None
    store.token_path()
    Path(store.token_path()).parent.mkdir(parents=True, exist_ok=True)
    Path(store.token_path()).write_text("   \n", encoding="utf-8")
    assert store.read_token() is None
    assert store.token_status()["active"] is False


def test_write_is_atomic_and_replaces_previous_token(store):
    old = store.write_token("old-token")
    new = store.write_token("new-token")
    assert old == new
    assert store.read_token() == "new-token"
    assert not list(Path(store.token_path()).parent.glob("*.tmp"))


def test_write_does_not_leave_tmp_file_on_failure(store, monkeypatch):
    store.write_token("keep-me")
    real_replace = os.replace

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.write_token("lost")
    monkeypatch.setattr(os, "replace", real_replace)
    assert store.read_token() == "keep-me"


def test_token_file_is_private_on_posix(store):
    if sys.platform == "win32":
        pytest.skip("POSIX permissions")
    store.write_token("secret")
    mode = stat.S_IMODE(os.stat(store.token_path()).st_mode)
    assert mode == 0o600


def test_revoke_removes_file(store):
    store.write_token("secret")
    assert store.revoke_token() is True
    assert store.read_token() is None
    assert store.revoke_token() is False


def test_generate_token_is_urlsafe_and_long(store):
    token = store.generate_token()
    assert len(token) >= 32
    assert " " not in token
    assert token != store.generate_token()


def test_token_path_uses_userprofile_when_appdata_missing(store, monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows path")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("USERPROFILE", r"C:\Users\someone")
    assert store.token_path().endswith(r"qgis-mcp\token")


def test_token_path_uses_xdg_config_home(store, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("POSIX path")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert store.token_path() == "/tmp/xdg/qgis-mcp/token"


def test_read_token_survives_an_unresolvable_home(store, monkeypatch):
    """The auth gate reads per command: a broken environment must not raise."""

    def no_home():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(store, "_config_root", no_home)
    assert store.read_token() is None
    assert store.token_status()["active"] is False
