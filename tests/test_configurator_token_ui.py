import ast
from pathlib import Path

CONFIGURATOR = Path(__file__).resolve().parents[1] / "qgis_listener" / "configurator.py"


def _tree():
    return ast.parse(CONFIGURATOR.read_text(encoding="utf-8"))


def _method_names():
    return {node.name for node in ast.walk(_tree()) if isinstance(node, ast.FunctionDef)}


def _source():
    return CONFIGURATOR.read_text(encoding="utf-8")


def test_token_methods_exist():
    assert {
        "_token_group",
        "_refresh_token_state",
        "_on_generate_token",
        "_on_revoke_token",
        "_on_copy_token",
        "_on_toggle_token_visibility",
    } <= _method_names()


def test_token_widgets_exist():
    source = _source()
    for name in (
        "token_status_label",
        "token_edit",
        "token_show_btn",
        "token_copy_btn",
        "token_generate_btn",
        "token_revoke_btn",
        "token_path_label",
    ):
        assert name in source


def test_token_field_is_masked_and_has_a_show_toggle():
    source = _source()
    assert "QLineEdit" in source
    assert "ECHO_PASSWORD" in source
    assert "ECHO_NORMAL" in source
    assert "Show" in source
    assert "Hide" in source


def test_token_actions_call_the_store():
    source = _source()
    for call in ("read_token", "write_token", "generate_token", "revoke_token", "token_status"):
        assert call in source


def test_token_is_never_written_to_qgssettings():
    source = _source()
    assert "SETTINGS_PREFIX}/token" not in source


def _qgssettings_writes(source):
    """Every key expression passed to a QSettings `setValue` call."""
    keys = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name in {"setValue", "set_value"} and node.args:
            keys.append(ast.unparse(node.args[0]))
    return keys


def test_the_qgssettings_guard_would_catch_a_token_write():
    """The assertion above is a substring match; this pins that it has teeth."""
    planted = """
def save(self):
    QgsSettings().setValue(f"{SETTINGS_PREFIX}/token", self.token_edit.text())
"""
    written = _qgssettings_writes(planted)
    assert len(written) == 1, written
    # `ast.unparse` normalises the quotes; the key text is what matters.
    assert "SETTINGS_PREFIX}/token" in written[0], written
    assert any("token" in key for key in written)


def test_qgssettings_only_stores_non_secret_settings():
    writes = _qgssettings_writes(_source())
    assert writes, "no setValue calls found: the detector is looking at nothing"
    assert not any("token" in key.lower() for key in writes), writes


def _token_mutations():
    """The two token slots, so the guard below cannot pass on a rename alone."""
    return {
        node.name: node
        for node in ast.walk(_tree())
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_on_generate_token", "_on_revoke_token"}
    }


def _inside_try(func, names):
    """True when every call to one of *names* inside *func* sits in a `try`."""
    calls, guarded = [], set()
    for node in ast.walk(func):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                guarded.add(id(child))
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in names:
                calls.append((name, id(node)))
    return calls and all(call_id in guarded for _, call_id in calls)


def test_token_mutations_cannot_abort_qgis():
    """`write_token`/`revoke_token` can raise OSError (read-only profile, AV lock).

    An exception escaping a PyQt slot calls qFatal: the dialog would take QGIS
    down instead of telling the user the token was not saved.
    """
    mutations = _token_mutations()
    assert set(mutations) == {"_on_generate_token", "_on_revoke_token"}
    for method in ("_on_generate_token", "_on_revoke_token"):
        assert _inside_try(mutations[method], {"write_token", "revoke_token"}), method


def test_no_pyqt5_only_exec_underscore_in_plugin():
    # PyQt6 (QGIS 4.x) removed exec_(); only exec() exists on both.
    for path in (CONFIGURATOR.parent).glob("**/*.py"):
        assert ".exec_(" not in path.read_text(encoding="utf-8"), path


def test_refresh_token_state_clears_the_error_stylesheet():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == "_refresh_token_state":
            assert 'setStyleSheet("")' in ast.get_source_segment(_source(), node)
            return
    raise AssertionError("_refresh_token_state not found")


def test_button_label_resets_do_not_use_orphan_single_shots():
    # A bare QTimer.singleShot lambda can fire after the dialog is deleted.
    assert "QTimer.singleShot" not in _source()


def test_plugin_uses_one_log_tag():
    plugin_dir = CONFIGURATOR.parent
    for name in ("plugin.py", "configurator.py", "compat.py"):
        assert '"MCP",' not in (plugin_dir / name).read_text(encoding="utf-8"), name


def test_plugin_startup_timers_are_stopped_on_unload():
    source = (CONFIGURATOR.parent / "plugin.py").read_text(encoding="utf-8")
    assert "QTimer.singleShot" not in source
    unload = source.split("def unload", 1)[1]
    assert "_startup_timers" in unload
