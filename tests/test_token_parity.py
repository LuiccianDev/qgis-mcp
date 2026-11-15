"""The plugin and the MCP server each ship a copy of the token store.

Two install paths (QGIS Plugin Manager, the uv cache) mean the two files can
drift even though only one needs to change. These tests pin the parts that
must never diverge: the constants that define where the token lives, and the
public functions the configurator and the protocol layer call.
"""

import importlib.util
from pathlib import Path

from qgis_mcp import token_store as server_store

REPO = Path(__file__).resolve().parents[1]
PLUGIN_STORE = REPO / "qgis_listener" / "token_store.py"

PUBLIC = (
    "ENV_VAR",
    "APP_DIR_NAME",
    "TOKEN_FILENAME",
    "token_path",
    "read_token",
    "generate_token",
    "write_token",
    "revoke_token",
    "token_status",
)


def _load_plugin_store():
    spec = importlib.util.spec_from_file_location("plugin_token_store", PLUGIN_STORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_constants_match():
    plugin = _load_plugin_store()
    assert plugin.ENV_VAR == server_store.ENV_VAR == "QGIS_MCP_TOKEN"
    assert plugin.APP_DIR_NAME == server_store.APP_DIR_NAME == "qgis-mcp"
    assert plugin.TOKEN_FILENAME == server_store.TOKEN_FILENAME == "token"


def test_public_surface_matches():
    plugin = _load_plugin_store()
    for name in PUBLIC:
        assert hasattr(plugin, name), f"plugin token_store lost {name}"
        assert hasattr(server_store, name), f"server token_store lost {name}"
