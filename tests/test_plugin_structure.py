"""Static guards on the plugin package's structure.

The handlers live in ``qgis_listener/handlers/`` as mixins combined onto
``QgisMCPServer``. None of that can be imported here (it needs ``qgis``), so
these checks are AST-based, like ``test_py39_compat.py``.
"""

import ast
import os
import re

HERE = os.path.dirname(__file__)
PLUGIN_DIR = os.path.join(HERE, "..", "qgis_listener")
HANDLERS_DIR = os.path.join(PLUGIN_DIR, "handlers")
MCP_SRC = os.path.join(HERE, "..", "src", "qgis_mcp")

# Modules that sit in the plugin package root. A module inside handlers/ must
# reach them with two dots; one dot resolves inside handlers/ and fails at
# import time - which no compile check or unit test catches, because the plugin
# is only ever imported by QGIS.
PACKAGE_ROOT_MODULES = ("compat", "constants", "errors", "registry", "wire")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _handler_modules():
    for name in sorted(os.listdir(HANDLERS_DIR)):
        if name.endswith(".py") and name != "__init__.py":
            yield name, _read(os.path.join(HANDLERS_DIR, name))


def _command_sources():
    """Every module that may register wire commands: the mixins plus server.py."""
    yield from _handler_modules()
    yield "server.py", _read(os.path.join(PLUGIN_DIR, "server.py"))


def _is_command_decorator(node):
    """True for `@command` and for an attribute access ending in `.command`."""
    return (getattr(node, "id", None) or getattr(node, "attr", None)) == "command"


def _registered_commands():
    commands = {}
    for name, src in _command_sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.FunctionDef):
                continue
            # Bare `@command` today; `@registry.command` would be an Attribute,
            # and matching only the Name form would silently pass on every module.
            if any(_is_command_decorator(d) for d in node.decorator_list):
                commands.setdefault(node.name, []).append(name)
    return commands


def _mcp_server_tool_sources():
    """Source files that define granular MCP tools (server.py and tools/*.py)."""
    yield _read(os.path.join(MCP_SRC, "server.py"))
    tools_dir = os.path.join(MCP_SRC, "tools")
    if os.path.isdir(tools_dir):
        for fname in sorted(os.listdir(tools_dir)):
            if fname.endswith(".py"):
                yield _read(os.path.join(tools_dir, fname))


def _commands_the_server_sends():
    """Command names the MCP server puts on the wire, from its own source."""
    sent = set()
    sources = list(_mcp_server_tool_sources())
    sources.append(_read(os.path.join(MCP_SRC, "compound_tools.py")))
    for src in sources:
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            called = getattr(func, "id", None) or getattr(func, "attr", None)
            if called in ("_send", "_send_sync", "send_command"):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    sent.add(first.value)
    return sent


def _one_dot_imports(src):
    """``from .x import ...`` nodes - one dot resolves inside handlers/."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            yield node


def test_handler_modules_reach_the_package_root_with_two_dots():
    """`from .compat import ...` inside handlers/ is an ImportError at load time."""
    offenders = []
    for name, src in _handler_modules():
        for node in _one_dot_imports(src):
            if node.module in PACKAGE_ROOT_MODULES:
                offenders.append(f"handlers/{name}:{node.lineno} from .{node.module}")
    assert not offenders, (
        "handlers/ is a subpackage: these must import from '..' instead of '.', "
        f"or QGIS fails to load the plugin: {offenders}"
    )


def test_handler_mixins_do_not_import_each_other():
    """The mixins are siblings on one class; they must not depend on each other.

    Shared helpers belong in ``handlers/base.py`` (``HandlerBase``), which is
    last in the MRO, so any mixin can call them through ``self``.
    """
    offenders = []
    for name, src in _handler_modules():
        for node in _one_dot_imports(src):
            if node.module not in PACKAGE_ROOT_MODULES:
                offenders.append(f"handlers/{name}:{node.lineno} imports .{node.module}")
    assert not offenders, f"handler mixins must not import one another: {offenders}"


def test_command_names_are_unique():
    """Two mixins registering the same name would silently shadow by MRO order."""
    dupes = {n: mods for n, mods in _registered_commands().items() if len(mods) > 1}
    assert not dupes, f"the same command is registered in more than one module: {dupes}"


def test_every_command_the_mcp_server_sends_is_registered():
    """A command the server sends but the plugin does not register is dead on arrival."""
    missing = sorted(_commands_the_server_sends() - set(_registered_commands()))
    assert not missing, (
        f"src/qgis_mcp sends these commands but no @command handler exists for them: {missing}"
    )


def test_every_registered_command_is_reachable_from_the_mcp_server():
    """The reverse: a handler nothing can call is either dead code or a missing tool."""
    unreachable = sorted(set(_registered_commands()) - _commands_the_server_sends())
    assert not unreachable, (
        "these handlers are registered but src/qgis_mcp never sends them - add the "
        f"tool or drop the handler: {unreachable}"
    )


def test_dispatch_only_reaches_decorated_handlers():
    """Dispatch must gate getattr on COMMANDS, or any attribute becomes callable.

    Without the membership test a client could send ``{"type": "stop"}`` and
    reach the server's own methods.
    """
    src = _read(os.path.join(PLUGIN_DIR, "server.py"))
    start = src.index("def _dispatch")
    dispatch = src[start:]
    marker = "\n    @command"
    if marker in dispatch:
        end = dispatch.index(marker)
        dispatch = dispatch[:end]
    assert "cmd_type not in COMMANDS" in dispatch, (
        "_dispatch must reject command names that are not in the COMMANDS registry"
    )
    assert re.search(r"getattr\(self, cmd_type\)", dispatch), (
        "_dispatch is expected to resolve the handler with getattr after the COMMANDS check"
    )


def _raises_command_error(node):
    """True for `raise CommandError(...)` / `raise LayerNotFound(...)` and friends."""
    exc = node.exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    name = getattr(exc, "id", None) or getattr(exc, "attr", None)
    return name in ("CommandError", "LayerNotFound", "WrongLayerType")


def _has_command_error_raise(*roots):
    """True when any node under *roots* is `raise CommandError(...)`-like."""
    for root in roots:
        for node in ast.walk(root):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            if _raises_command_error(node):
                return True
    return False


def _catches(handler, *names):
    caught = handler.type
    if caught is None:
        return "Exception" in names  # bare `except:` behaves like except Exception
    parts = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return any((getattr(p, "id", None) or getattr(p, "attr", None)) in names for p in parts)


def test_deliberate_command_errors_are_not_rewrapped():
    """A `try` that raises CommandError itself must re-raise it before the catch-all.

    ``except Exception as e: raise CommandError(f"Processing error: {e}")`` also
    catches the handler's *own* deliberate message, so a clean "Processing
    cancelled after 55s, pass a larger timeout" came back to the user as
    "Processing error: Processing cancelled after 55s" - reading as if the
    timeout were an internal failure. Re-raise CommandError untouched first.
    """
    offenders = []
    for name, src in _command_sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Try):
                continue
            raised_here = _has_command_error_raise(*node.body)
            rewraps = any(
                _catches(h, "Exception") and _has_command_error_raise(h) for h in node.handlers
            )
            passes_through = any(_catches(h, "CommandError") for h in node.handlers)
            if raised_here and rewraps and not passes_through:
                offenders.append(f"{name}:{node.lineno}")
    assert not offenders, (
        "these try blocks raise a CommandError and then re-wrap it in their own "
        f"catch-all - add `except CommandError: raise` first: {offenders}"
    )


def _commands_of_read_only_tools():
    """Commands sent by granular tools annotated readOnlyHint=True."""
    commands = set()
    for src in _mcp_server_tool_sources():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            tools = [
                d
                for d in node.decorator_list
                if isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "tool"
            ]
            read_only = tools and any(
                isinstance(k, ast.keyword)
                and k.arg == "readOnlyHint"
                and getattr(k.value, "value", None) is True
                for k in ast.walk(tools[0])
            )
            if not read_only:
                continue
            for call in ast.walk(node):
                func = getattr(call, "func", None)
                called = getattr(func, "id", None) or getattr(func, "attr", None)
                if called in ("_send", "_send_sync") and call.args:
                    commands.add(call.args[0].value)
    return commands


def test_the_journal_leaves_out_exactly_the_read_only_commands():
    """export_session replays what changed something: the read-only tools' commands.

    Anything else in UNRECORDED_COMMANDS has to be listed here on purpose.
    """
    bookkeeping = {
        "batch",
        "cancel_processing_job",
        "create_checkpoint",
        "export_session",
        "restore_checkpoint",
        "start_processing_job",
    }
    tree = ast.parse(_read(os.path.join(PLUGIN_DIR, "wire.py")))
    unrecorded = next(
        ast.literal_eval(node.value.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and node.targets[0].id == "UNRECORDED_COMMANDS"
    )
    assert unrecorded - bookkeeping == _commands_of_read_only_tools()


def test_mcp_fastmcp_shim_is_centralized_in_tools_base():
    """Only tools/base.py should contain the mcp.server.fastmcp Context/FastMCP fallback."""
    from pathlib import Path

    src_root = Path(MCP_SRC).resolve()
    offenders = []
    for path in sorted(src_root.rglob("*.py")):
        if path.name == "base.py" and path.parent.name == "tools":
            continue
        text = path.read_text(encoding="utf-8")
        if "from mcp.server.mcpserver import Context" in text or "MCPServer as FastMCP" in text:
            offenders.append(path.name)
    assert offenders == [], f"Duplicate FastMCP/Context shim found in: {offenders}"


def test_pyproject_exposes_luiccian_qgis_mcp_script_and_qgis_mcp_package():
    """pyproject.toml names the distribution luiccian-qgis-mcp with package src/qgis_mcp."""
    import tomllib
    from pathlib import Path

    repo_root = Path(HERE).resolve().parent
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "luiccian-qgis-mcp"
    assert data["project"]["scripts"] == {"luiccian-qgis-mcp": "qgis_mcp.server:main"}
    assert data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/qgis_mcp"]


def test_configurator_jsonc_and_merge_helpers(tmp_path, plugin_handlers, monkeypatch):
    """read_jsonc supports comments/trailing commas and merge_qgis_entry backs up & replaces non-dicts."""
    import sys

    from conftest import FakeQObject

    monkeypatch.setattr(sys.modules["qgis.PyQt.QtWidgets"], "QDialog", FakeQObject, raising=False)
    from qgis_listener.configurator import (
        backup_config,
        has_qgis_entry,
        merge_qgis_entry,
        read_jsonc,
    )

    cfg = tmp_path / "settings.json"
    cfg.write_text(
        '{\n  // Zed style comment\n  "context_servers": ["broken"],\n}\n',
        encoding="utf-8",
    )
    data = read_jsonc(cfg)
    assert data == {"context_servers": ["broken"]}

    bak = backup_config(cfg)
    assert bak is not None and bak.exists()

    merge_qgis_entry(data, "context_servers", {"command": "uvx"})
    assert data["context_servers"] == {"qgis": {"command": "uvx"}}
    assert has_qgis_entry(data, "context_servers") is True


def test_constants_and_handler_base_expose_shared_helpers():
    """Shared constants live in constants.py and cross-mixin helpers live on HandlerBase."""
    constants_src = _read(os.path.join(PLUGIN_DIR, "constants.py"))
    assert "LOG_TAG =" in constants_src
    assert "REPO_URL =" in constants_src

    base_tree = ast.parse(_read(os.path.join(HANDLERS_DIR, "base.py")))
    base_methods = {node.name for node in ast.walk(base_tree) if isinstance(node, ast.FunctionDef)}
    for helper in (
        "_field_index",
        "_extent_dict",
        "_provider_mutate",
        "_refresh_layer_symbology",
    ):
        assert helper in base_methods, f"Missing shared helper on HandlerBase: {helper}"


def test_all_handler_methods_stay_concise():
    """No handler helper or command exceeds 80 lines."""
    offenders = []
    for name, src in _handler_modules():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef):
                length = node.end_lineno - node.lineno + 1
                if length > 80:
                    offenders.append(f"handlers/{name}:{node.name} ({length}L)")
    assert not offenders, f"Oversized handler methods (>80L): {offenders}"


def test_plugin_root_modules_stay_concise():
    """No function or method in configurator.py, plugin.py, or server.py exceeds 80 lines."""
    offenders = []
    for name in ("configurator.py", "plugin.py", "server.py"):
        src = _read(os.path.join(PLUGIN_DIR, name))
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef):
                length = node.end_lineno - node.lineno + 1
                if length > 80:
                    offenders.append(f"{name}:{node.name} ({length}L)")
    assert not offenders, f"Oversized root module methods (>80L): {offenders}"


def test_mcp_core_modules_stay_concise():
    """No function or method in client.py, helpers.py, protocol.py, or server.py exceeds 80 lines."""
    offenders = []
    for name in ("client.py", "helpers.py", "protocol.py", "server.py"):
        src = _read(os.path.join(MCP_SRC, name))
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1
                if length > 80:
                    offenders.append(f"{name}:{node.name} ({length}L)")
    assert not offenders, f"Oversized core MCP functions (>80L): {offenders}"


def test_compound_tools_is_structured_without_c901_noqa():
    """compound_tools.py must not suppress C901 and no method may exceed 120 lines."""
    src = _read(os.path.join(MCP_SRC, "compound_tools.py"))
    assert "noqa: C901" not in src, "compound_tools.py should not need # noqa: C901"
    offenders = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = node.end_lineno - node.lineno + 1
            if length > 120:
                offenders.append(f"compound_tools.py:{node.name} ({length}L)")
    assert not offenders, f"Oversized functions in compound_tools.py (>120L): {offenders}"


def test_all_toolset_methods_stay_concise():
    """No registration method in src/qgis_mcp/tools/ exceeds 115 lines, and no tool function exceeds 80 lines."""
    tools_dir = os.path.join(MCP_SRC, "tools")
    offenders = []
    for fname in sorted(os.listdir(tools_dir)):
        if not fname.endswith(".py"):
            continue
        src = _read(os.path.join(tools_dir, fname))
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1
                limit = 115 if node.name.startswith(("register", "_register")) else 80
                if length > limit:
                    offenders.append(f"tools/{fname}:{node.name} ({length}L > {limit}L)")
    assert not offenders, f"Oversized toolset methods: {offenders}"


def test_handlers_avoid_deprecated_qgsfield_and_band_statistics():
    """Handlers use compat.make_field and 4-arg bandStatistics(band, stats, extent, sampleSize)."""
    qgsfield_offenders = []
    bandstats_offenders = []
    for name, src in _handler_modules():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "QgsField":
                qgsfield_offenders.append(f"handlers/{name}:{node.lineno}")
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "bandStatistics"
                and len(node.args) < 4
                and "extent" not in {kw.arg for kw in node.keywords}
            ):
                bandstats_offenders.append(f"handlers/{name}:{node.lineno}")
    assert not qgsfield_offenders, f"Direct QgsField() call in handlers: {qgsfield_offenders}"
    assert not bandstats_offenders, (
        f"Deprecated 2-arg bandStatistics() call in handlers: {bandstats_offenders}"
    )
