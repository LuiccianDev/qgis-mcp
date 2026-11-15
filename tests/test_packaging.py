"""The published package must hold the server and nothing else.

The repository also carries the QGIS plugin and the whole test suite. Neither
belongs in the wheel: the plugin is installed by QGIS from a ZIP, and the tests
are source-only. The root LICENSE is the only license file for the
distribution, so the copy that used to sit inside the package must stay gone.
"""

import ast
import importlib.util
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"


def _build():
    import shutil

    uv = shutil.which("uv")
    if uv:
        cmd = [uv, "build", "--wheel", "--sdist", "--out-dir", str(DIST)]
    else:
        cmd = [sys.executable, "-m", "build", "--wheel", "--sdist", "--outdir", str(DIST)]
    subprocess.run(cmd, cwd=REPO, check=True)


def test_wheel_contains_only_the_server_package():
    _build()
    wheel = max(DIST.glob("luiccian_qgis_mcp-*.whl"), key=lambda p: p.stat().st_mtime)
    names = zipfile.ZipFile(wheel).namelist()
    assert any(n.startswith("qgis_mcp/") for n in names)
    assert not any(n.endswith("qgis_listener") or "/qgis_listener/" in n for n in names)
    # Wheel entries are relative to the package root: `src/` is not in the name.
    assert "qgis_mcp/LICENSE" not in names
    assert not any("__pycache__" in n for n in names)


def test_sdist_carries_no_plugin_copy():
    _build()
    sdist = max(DIST.glob("luiccian_qgis_mcp-*.tar.gz"), key=lambda p: p.stat().st_mtime)
    with tarfile.open(sdist) as tf:
        names = [n.split("/", 1)[-1] for n in tf.getnames()]
    # The plugin travels as its own ZIP, so neither its code nor its LICENSE
    # (a second copy of the same GPL text) belongs in the source archive.
    assert not any(n == "qgis_listener" or n.startswith("qgis_listener/") for n in names)
    for required in ("CHANGELOG.md", "LICENSE", "NOTICE", "README.md", "pyproject.toml"):
        assert required in names


def test_notice_keeps_attribution():
    notice = REPO / "NOTICE"
    assert notice.is_file(), "NOTICE file must exist at repo root"
    text = notice.read_text(encoding="utf-8")
    assert "LuiccianDev" in text
    assert "Apache-2.0" in text
    assert "GPL" in text
    assert "QGIS" in text
    assert "Nicolas Karasiak" not in text
    assert "nkarasiak" not in text.lower()


def test_server_package_has_no_qgis_or_plugin_imports():
    """Apache-2.0 server code must never import PyQGIS, PyQt, or qgis_listener."""
    forbidden = {"qgis", "PyQt5", "PyQt6", "sip", "qgis_listener"}
    offenders = []
    for path in (REPO / "src" / "qgis_mcp").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden:
                        offenders.append(f"{path.relative_to(REPO)}: import {alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] in forbidden
            ):
                offenders.append(f"{path.relative_to(REPO)}: from {node.module}")
    assert not offenders, offenders


def test_dual_license_files_and_metadata():
    """Root/server is Apache-2.0 while qgis_listener/ remains GPLv2+."""
    root_license = (REPO / "LICENSE").read_text(encoding="utf-8")
    plugin_license = (REPO / "qgis_listener" / "LICENSE").read_text(encoding="utf-8")
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")

    assert "Apache License" in root_license and "Version 2.0" in root_license
    assert "GNU GENERAL PUBLIC LICENSE" in plugin_license
    assert 'license = { text = "Apache-2.0" }' in pyproject


def test_plugin_zip_includes_gpl_license(tmp_path):
    """Plugin ZIP must carry its own GPLv2+ LICENSE file."""
    spec = importlib.util.spec_from_file_location(
        "build_plugin_zip", REPO / "scripts" / "build_plugin_zip.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    archive = mod.build(tmp_path)
    names = zipfile.ZipFile(archive).namelist()
    assert "qgis_listener/LICENSE" in names
    assert "qgis_listener/metadata.txt" in names


def _conftest_names(constant):
    """Read one of conftest's module lists without importing it."""
    tree = ast.parse((REPO / "tests" / "conftest.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == constant for target in node.targets
        ):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"{constant} is not defined at module level in tests/conftest.py")


def test_every_test_module_is_classified_as_plugin_dependent_or_not():
    """The sdist ships `tests/`, and the plugin does not travel with it.

    A test module that imports `qgis_listener/` must be skipped - or not
    collected at all - when the plugin is absent, otherwise the source archive
    hands the reader a suite that errors on its first run. The two lists in
    `conftest.py` are that decision; this test forces a new module to pick a
    side instead of defaulting to whatever the author's checkout happened to
    contain.
    """
    on_disk = {path.name for path in (REPO / "tests").glob("test_*.py")}
    plugin = set(_conftest_names("PLUGIN_TESTS"))
    plugin_free = set(_conftest_names("PLUGIN_FREE_TESTS"))

    assert not plugin & plugin_free, f"classified twice: {sorted(plugin & plugin_free)}"
    assert set(_conftest_names("COLLECT_IGNORE_WITHOUT_PLUGIN")) <= plugin
    assert plugin | plugin_free == on_disk, {
        "unclassified": sorted(on_disk - plugin - plugin_free),
        "stale": sorted((plugin | plugin_free) - on_disk),
    }
