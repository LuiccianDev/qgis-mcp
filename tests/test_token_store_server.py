import pytest

from qgis_mcp import token_store


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.delenv("QGIS_MCP_TOKEN", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(token_store, "_config_root", lambda: tmp_path / "config")
    return token_store


def test_roundtrip(store):
    store.write_token("abc123")
    assert store.read_token() == "abc123"
    assert store.token_status()["source"] == "file"


def test_revoke(store):
    store.write_token("abc123")
    assert store.revoke_token() is True
    assert store.read_token() is None


def test_env_wins_over_file(store, monkeypatch):
    store.write_token("from-file")
    monkeypatch.setenv("QGIS_MCP_TOKEN", "from-env")
    assert store.read_token() == "from-env"
    assert store.token_status()["source"] == "env"


def test_read_token_survives_an_unresolvable_home(monkeypatch):
    """The auth gate reads per command: a broken environment must not raise."""
    monkeypatch.delenv("QGIS_MCP_TOKEN", raising=False)

    def no_home():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(token_store, "_config_root", no_home)
    assert token_store.read_token() is None
