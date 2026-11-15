"""Unit tests for install.py: JSONC stripping, atomic config writes, config merge."""

import argparse
import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install


def test_jsonc_keeps_comment_markers_inside_strings():
    text = '{"glob": "/*.log", "b": "x*/y", "url": "https://x/y", "ok": 1}'
    assert json.loads(install._jsonc_to_json(text)) == {
        "glob": "/*.log",
        "b": "x*/y",
        "url": "https://x/y",
        "ok": 1,
    }


def test_jsonc_strips_comments_and_trailing_commas():
    text = """{
        // line comment
        "a": 1, /* block
        spanning lines */
        "b": [1, 2,],
    }"""
    assert json.loads(install._jsonc_to_json(text)) == {"a": 1, "b": [1, 2]}


def test_write_json_is_atomic(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    install._write_json(path, {"new": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
    assert list(tmp_path.iterdir()) == [path], "temp file left behind"


def test_write_json_leaves_original_when_serialization_fails(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    try:
        install._write_json(path, {"bad": object()})
    except TypeError:
        pass
    else:
        raise AssertionError("expected TypeError on unserializable value")

    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}


def test_configure_client_merges_into_existing_config(tmp_path, monkeypatch):
    path = tmp_path / "cursor.json"
    path.write_text(
        json.dumps({"other": 1, "mcpServers": {"keepme": {"command": "x"}}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        install, "_client_registry", lambda: {"cursor": {"path": path, "key": "mcpServers"}}
    )

    install.configure_client("cursor", remote=True)

    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["other"] == 1
    assert config["mcpServers"]["keepme"] == {"command": "x"}
    assert config["mcpServers"]["qgis"] == install._remote_entry()
    assert list(tmp_path.glob("cursor.json.bak-*")), "no backup written"


def test_unconfigure_client_drops_empty_key(tmp_path, monkeypatch):
    path = tmp_path / "cursor.json"
    path.write_text(json.dumps({"mcpServers": {"qgis": {"command": "uvx"}}}), encoding="utf-8")
    monkeypatch.setattr(
        install, "_client_registry", lambda: {"cursor": {"path": path, "key": "mcpServers"}}
    )

    install.unconfigure_client("cursor")

    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_remove_target_asks_before_deleting_a_real_directory(tmp_path, monkeypatch):
    target = tmp_path / "qgis_listener"
    target.mkdir()
    (target / "metadata.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda *a: "n")

    try:
        install._remove_target(target)
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit when the user declines")
    assert target.exists()

    monkeypatch.setattr("builtins.input", lambda *a: "y")
    install._remove_target(target)
    assert not target.exists()


def test_remove_target_never_asks_for_a_symlink(tmp_path):
    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation needs developer mode or admin rights on Windows")
    install._remove_target(link)  # input() would raise OSError under pytest
    assert not link.is_symlink()


def test_plugin_target_is_qgis_listener(monkeypatch, tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "qgis_listener").mkdir()
    monkeypatch.setattr(install, "qgis_plugins_dir", lambda *a, **k: plugins)
    install.uninstall_plugin("default", "3", force=True)
    assert not (plugins / "qgis_listener").exists()
    assert not (plugins / "qgis_mcp_plugin").exists()


def test_remote_entry_uses_new_script():
    entry = install._remote_entry()
    assert entry["args"][-1] == "luiccian-qgis-mcp"
    assert "LuiccianDev/qgis-mcp" in entry["args"][1]


def test_github_url_points_at_the_new_repo():
    assert (
        install.GITHUB_URL
        == "https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip"
    )


def test_configure_client_replaces_a_non_dict_key(tmp_path, monkeypatch):
    path = tmp_path / "zed.json"
    path.write_text(json.dumps({"context_servers": ["oops"]}), encoding="utf-8")
    monkeypatch.setattr(
        install, "_client_registry", lambda: {"zed": {"path": path, "key": "context_servers"}}
    )

    install.configure_client("zed", remote=True)

    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["context_servers"] == {"qgis": install._remote_entry()}


def test_backup_does_not_overwrite_an_earlier_backup(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text("first", encoding="utf-8")
    install._backup(path)
    path.write_text("second", encoding="utf-8")
    install._backup(path)

    saved = sorted(b.read_text(encoding="utf-8") for b in tmp_path.glob("mcp.json.bak*"))
    assert saved == ["first", "second"]


def test_one_malformed_config_does_not_stop_the_next_client(tmp_path, monkeypatch, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json at all", encoding="utf-8")
    good = tmp_path / "good.json"
    monkeypatch.setattr(
        install,
        "_client_registry",
        lambda: {
            "broken": {"path": broken, "key": "mcpServers"},
            "good": {"path": good, "key": "mcpServers"},
        },
    )
    args = argparse.Namespace(uninstall=False, non_interactive=True, remote=True)

    install._do_clients(args, ["broken", "good"])

    config = json.loads(good.read_text(encoding="utf-8"))
    assert config["mcpServers"]["qgis"] == install._remote_entry()
    assert "Skipped broken" in capsys.readouterr().out


# ── configurator / installer client parity ──────────────────────────────────
#
# The plugin ships without install.py, so the QGIS dialog carries its own copy
# of the client list and the two drift silently.  Issue #50: codex sat in
# install.py's registry while the dialog's dropdown never offered it.  The
# dialog needs qgis to import, so these read it as source.

CONFIGURATOR = Path(__file__).resolve().parents[1] / "qgis_listener" / "configurator.py"


def _configurator_ast():
    return ast.parse(CONFIGURATOR.read_text(encoding="utf-8"))


def _configurator_registry_clients():
    for node in ast.walk(_configurator_ast()):
        if isinstance(node, ast.FunctionDef) and node.name == "_client_config_registry":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                    return {k.value for k in sub.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("_client_config_registry's return dict not found")


def _configurator_dropdown_clients():
    for node in ast.walk(_configurator_ast()):
        if not isinstance(node, ast.Call) or getattr(node.func, "attr", None) != "addItems":
            continue
        if not node.args or not isinstance(node.args[0], ast.List):
            continue
        # Two addItems calls exist; the mode selector's has no client names.
        names = {e.value for e in node.args[0].elts if isinstance(e, ast.Constant)}
        if "claude-code" in names:
            return names
    raise AssertionError("client_combo.addItems list not found")


def test_configurator_dropdown_matches_its_own_registry():
    assert _configurator_dropdown_clients() == _configurator_registry_clients()


def test_supported_clients_are_exclusively_antigravity_claude_and_manual():
    expected = {"antigravity", "claude-desktop", "claude-code", "manual"}
    reg = install._client_registry()
    assert set(reg.keys()) == expected
    assert set(install.ALL_CLIENTS) == expected
    assert _configurator_registry_clients() == expected
    assert _configurator_dropdown_clients() == expected
    assert reg["antigravity"]["key"] == "mcpServers"
    assert Path(reg["antigravity"]["path"]).name == "mcp_config.json"
    assert reg["claude-desktop"]["key"] == "mcpServers"
    assert reg["claude-code"].get("print_only") is True
    assert reg["manual"].get("print_only") is True


# ── ZIP & remote release plugin installation ────────────────────────────────


def test_install_plugin_from_zip_extracts_valid_archive(tmp_path, monkeypatch):
    import zipfile

    plugins_dir = tmp_path / "plugins"
    monkeypatch.setattr(install, "qgis_plugins_dir", lambda profile, version="auto": plugins_dir)

    archive = tmp_path / "qgis_listener_v1-0-0.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("qgis_listener/metadata.txt", "[general]\nversion=1.0.0\n")
        zf.writestr("qgis_listener/__init__.py", "# init\n")

    target = install.install_plugin_from_zip(archive, profile="default", force=True)

    assert target == plugins_dir / "qgis_listener"
    assert (target / "metadata.txt").is_file()
    assert not target.is_symlink()


def test_install_plugin_from_zip_rejects_missing_metadata(tmp_path, monkeypatch):
    import zipfile

    plugins_dir = tmp_path / "plugins"
    monkeypatch.setattr(install, "qgis_plugins_dir", lambda profile, version="auto": plugins_dir)

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("other_folder/file.txt", "hello")

    with pytest.raises(SystemExit):
        install.install_plugin_from_zip(archive, profile="default", force=True)

    assert not (plugins_dir / "other_folder").exists()


def test_install_plugin_from_zip_rejects_path_traversal(tmp_path, monkeypatch):
    import zipfile

    plugins_dir = tmp_path / "plugins"
    monkeypatch.setattr(install, "qgis_plugins_dir", lambda profile, version="auto": plugins_dir)

    archive = tmp_path / "traversal.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("qgis_listener/metadata.txt", "[general]\nversion=1.0.0\n")
        zf.writestr("qgis_listener/../../evil.txt", "pwned")

    with pytest.raises(SystemExit):
        install.install_plugin_from_zip(archive, profile="default", force=True)

    assert not (tmp_path / "evil.txt").exists()


def test_install_plugin_from_zip_rejects_backslash_traversal(tmp_path, monkeypatch):
    import zipfile

    plugins_dir = tmp_path / "plugins"
    monkeypatch.setattr(install, "qgis_plugins_dir", lambda profile, version="auto": plugins_dir)

    archive = tmp_path / "backslash_traversal.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("qgis_listener/metadata.txt", "[general]\nversion=1.0.0\n")
        zf.writestr("qgis_listener/sub\\..\\..\\evil.txt", "pwned")

    with pytest.raises(SystemExit):
        install.install_plugin_from_zip(archive, profile="default", force=True)

    assert not (tmp_path / "evil.txt").exists()


def test_download_release_zip_handles_missing_asset(tmp_path, monkeypatch):
    import io

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=30: _Resp(b'{"assets": []}'),
    )

    with pytest.raises(SystemExit):
        install.download_release_zip(tmp_path)


def test_detect_qgis_installations_finds_profiles(tmp_path, monkeypatch):
    qgis3_profiles = tmp_path / "QGIS3" / "profiles"
    (qgis3_profiles / "default").mkdir(parents=True)
    (qgis3_profiles / "dev" / "python" / "plugins" / "qgis_listener").mkdir(parents=True)

    monkeypatch.setattr(install, "_qgis_base_dir", lambda version="3": tmp_path / f"QGIS{version}")
    found = install.detect_qgis_installations()
    assert len(found) == 1
    assert found[0]["version"] == "3"
    assert set(found[0]["profiles"]) == {"default", "dev"}
    assert "dev" in found[0]["installed_profiles"]


def test_format_manual_config_snippet_returns_valid_mcp_json():
    snippet = install.format_manual_config(remote=False)
    parsed = json.loads(snippet)
    assert "mcpServers" in parsed
    assert "qgis" in parsed["mcpServers"]
    assert "command" in parsed["mcpServers"]["qgis"]
