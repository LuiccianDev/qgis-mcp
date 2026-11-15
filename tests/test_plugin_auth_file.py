"""The plugin's auth gate reads the shared token file, not only the env var.

The `plugin_handlers` fixture stubs `qgis`, so the server can be constructed
and driven with a plain dict exactly as the socket loop drives it.
"""

import pytest


@pytest.fixture
def store(plugin_handlers, monkeypatch, tmp_path):
    from qgis_listener import token_store

    monkeypatch.delenv("QGIS_MCP_TOKEN", raising=False)
    monkeypatch.setattr(token_store, "_config_root", lambda: tmp_path / "config")
    return token_store


def _server(store):
    from qgis_listener.server import QgisMCPServer

    return QgisMCPServer(host="localhost", port=9878)


def test_plugin_accepts_token_from_file(store):
    server = _server(store)
    store.write_token("file-secret")
    ok = server.execute_command({"type": "ping", "token": "file-secret"})
    assert ok["status"] == "success"


def test_plugin_rejects_missing_token(store):
    server = _server(store)
    store.write_token("file-secret")
    bad = server.execute_command({"type": "ping"})
    assert bad["status"] == "error"
    assert "Authentication failed" in bad["message"]


def test_plugin_accepts_rotated_token(store):
    server = _server(store)
    store.write_token("old-token")
    assert server.execute_command({"type": "ping", "token": "old-token"})["status"] == "success"
    store.write_token("new-token")
    assert server.execute_command({"type": "ping", "token": "old-token"})["status"] == "error"
    assert server.execute_command({"type": "ping", "token": "new-token"})["status"] == "success"


def test_plugin_is_open_when_no_token_anywhere(store):
    server = _server(store)
    assert server.execute_command({"type": "ping"})["status"] == "success"
