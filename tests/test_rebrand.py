import configparser
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


def _load_plugin_constants():
    """Import `qgis_listener/constants.py` by path.

    ``qgis_listener/__init__.py`` imports the plugin, and therefore ``qgis``,
    so the package cannot be imported outside QGIS.
    """
    path = REPO / "qgis_listener" / "constants.py"
    spec = importlib.util.spec_from_file_location("qgis_listener_constants", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_upstream_imports():
    offenders = []
    paths = list(REPO.glob("src/**/*.py"))
    paths += list(REPO.glob("qgis_listener/**/*.py"))
    paths += [REPO / "install.py"]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        bad = "qgis_mcp_plugin" in text or "karasiak" in text.lower()
        if bad:
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, offenders


def test_default_port_and_unchanged_env_vars():
    from qgis_mcp import protocol

    assert protocol.DEFAULT_PORT == 9878
    with patch.dict(os.environ, {"QGIS_MCP_PORT": "9999"}, clear=True):
        from qgis_mcp.server import get_instances

        assert get_instances()["default"][1] == 9999


def test_plugin_defaults():
    constants = _load_plugin_constants()

    assert constants.DEFAULT_PORT == 9878
    assert constants.SETTINGS_PREFIX == "qgis_mcp"


def test_metadata_identity():
    cfg = configparser.ConfigParser()
    cfg.read(REPO / "qgis_listener" / "metadata.txt", encoding="utf-8")
    general = cfg["general"]
    assert general["name"] == "Luiccian QGIS Listener"
    assert general["version"] == "0.1.0"
    assert general["license"] == "GPLv2+"
    assert "supportsqt6" not in general
    assert "nkarasiak" not in general["homepage"]


def test_no_upstream_strings_in_docs_or_config():
    offenders = []
    paths = [
        REPO / "NOTICE",
        REPO / "README.md",
        REPO / "CHANGELOG.md",
        REPO / "AGENTS.md",
        REPO / "CONTRIBUTING.md",
        REPO / "docs" / "agent-integration.md",
        REPO / ".github" / "workflows" / "release.yml",
        REPO / ".github" / "workflows" / "tests.yml",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for bad in (
            "nkarasiak",
            "karasiak",
            "qgis_mcp_plugin",
            "plugins.qgis.org",
            "qgis-mcp-server",
        ):
            if bad in lowered:
                offenders.append(f"{path.relative_to(REPO)}: {bad}")
    assert not offenders, offenders
