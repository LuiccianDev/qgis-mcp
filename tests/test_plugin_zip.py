"""The plugin ZIP is the only artifact QGIS installs: it must be self-contained.

QGIS unzips the archive straight into the profile and imports `qgis_listener`,
so every entry has to sit under that folder, the license and metadata have to
travel with the code, and caches or development notes must not.
"""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_plugin_zip import build


def test_zip_root_is_the_plugin_folder(tmp_path):
    archive = build(tmp_path)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert names, "empty archive"
    assert all(name.startswith("qgis_listener/") for name in names)


def test_zip_contains_required_plugin_files(tmp_path):
    archive = build(tmp_path)
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
    assert "qgis_listener/metadata.txt" in names
    assert "qgis_listener/LICENSE" in names
    assert "qgis_listener/token_store.py" in names
    assert "qgis_listener/plugin.py" in names


def test_zip_excludes_caches_and_dev_docs(tmp_path):
    archive = build(tmp_path)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert not any(n.endswith("AGENTS.md") for n in names)


def test_zip_is_under_the_hub_limit(tmp_path):
    archive = build(tmp_path)
    assert archive.stat().st_size < 25 * 1024 * 1024


def test_release_script_checks_and_bumps_versions_consistently(tmp_path):
    from scripts import release

    repo_root = Path(__file__).resolve().parents[1]
    info = release.verify_repo_versions(repo_root)
    assert info["pyproject_version"] == info["metadata_version"]

    fake_repo = tmp_path / "repo"
    (fake_repo / "qgis_listener").mkdir(parents=True)
    (fake_repo / "pyproject.toml").write_text(
        '[project]\nname = "luiccian-qgis-mcp"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (fake_repo / "qgis_listener" / "metadata.txt").write_text(
        "[general]\nname=Luiccian QGIS Listener\nversion=0.1.0\nchangelog=0.1.0 : Initial\n",
        encoding="utf-8",
    )
    (fake_repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0] - 2026-04-17\n",
        encoding="utf-8",
    )

    release.set_repo_version(fake_repo, "0.2.0")
    updated = release.verify_repo_versions(fake_repo, expect_tag="v0.2.0")
    assert updated["pyproject_version"] == "0.2.0"
    assert updated["metadata_version"] == "0.2.0"


def test_github_workflows_enforce_security_testing_and_release_tag_verification():
    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / ".flake8").exists()
    assert not (repo_root / ".pre-commit-config.yaml").exists()

    tests_wf = (repo_root / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    release_wf = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "permissions:" in tests_wf and "contents: read" in tests_wf
    assert "concurrency:" in tests_wf
    assert "uv run --no-sync ruff check qgis_listener/ src/ tests/ install.py scripts/" in tests_wf
    assert (
        "uv run --no-sync ruff format --check qgis_listener/ src/ tests/ install.py scripts/"
        in tests_wf
    )
    assert "scripts/release.py --check" in tests_wf
    assert "--cov=src/qgis_mcp" in tests_wf
    assert "flake8" not in tests_wf and "bandit" not in tests_wf
    assert tests_wf.count("pytest tests/") == 1

    assert "uv run --no-sync ruff check" in release_wf
    assert "uv run --no-sync ruff format --check" in release_wf
    assert "scripts/release.py --check --expect-tag" in release_wf
    assert "pytest tests/" in release_wf
    assert "SHA256SUMS.txt" in release_wf
    assert "flake8" not in release_wf and "bandit" not in release_wf


def test_repository_has_no_unused_config_files_or_stale_doc_references():
    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / ".mcp.json").exists()
    assert not (repo_root / ".flake8").exists()
    assert not (repo_root / ".pre-commit-config.yaml").exists()

    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert ".mcp.json" in gitignore

    for doc_rel in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "docs/agent-integration.md"):
        content = (repo_root / doc_rel).read_text(encoding="utf-8")
        assert "src/luiccian_qgis_mcp" not in content, doc_rel
        assert ".flake8" not in content, doc_rel
        assert "flake8" not in content, doc_rel

    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    agent_doc = (repo_root / "docs" / "agent-integration.md").read_text(encoding="utf-8")
    for required in (
        "antigravity",
        "mcp_config.json",
        "claude-desktop",
        "claude-code",
        "scripts/build_plugin_zip.py",
        "--plugin-only --from-zip",
    ):
        assert required in readme, required
    for removed in ("opencode", "qgis-mcp-launch.bat", "kimi-code", "windsurf", "lmstudio"):
        assert removed not in readme, removed
        assert removed not in agent_doc, removed


def test_extract_changelog_section_returns_version_body_and_fallback(tmp_path):
    from scripts import release

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    (fake_repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [0.1.1] - 2026-11-15\n\n"
        "### Fixed\n- Fix A\n\n"
        "## [0.1.0] - 2026-11-10\n\nInitial.\n",
        encoding="utf-8",
    )

    body = release.extract_changelog_section(fake_repo, "v0.1.1")
    assert "### Fixed" in body
    assert "- Fix A" in body
    assert "## [0.1.0]" not in body

    missing = release.extract_changelog_section(fake_repo, "v9.9.9")
    assert "9.9.9" in missing


def test_bump_release_and_tests_support_workflow_call_without_pat():
    repo_root = Path(__file__).resolve().parents[1]
    tests_wf = (repo_root / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    bump_wf = (repo_root / ".github" / "workflows" / "bump-release.yml").read_text(encoding="utf-8")

    assert "workflow_call:" in tests_wf
    assert "uses: ./.github/workflows/tests.yml" in bump_wf
    assert "gh pr create" in bump_wf
    assert "--extract-notes" in bump_wf


def test_release_workflow_has_verify_build_gh_release_and_pypi_stages():
    repo_root = Path(__file__).resolve().parents[1]
    release_wf = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "v[0-9]+.[0-9]+.[0-9]+" in release_wf
    assert "workflow_dispatch:" in release_wf
    assert "verify-tag:" in release_wf
    assert "uv lock --check" in release_wf
    assert "pypa/gh-action-pypi-publish@" in release_wf
    assert "needs: [verify-tag, github-release]" in release_wf


def test_manual_publish_pypi_recovery_workflow_exists_and_supports_testpypi():
    repo_root = Path(__file__).resolve().parents[1]
    wf_path = repo_root / ".github" / "workflows" / "publish-pypi.yml"
    assert wf_path.is_file()
    content = wf_path.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in content
    assert "testpypi" in content
    assert "https://test.pypi.org/legacy/" in content
    assert "scripts/release.py --check --expect-tag" in content
    assert "pypa/gh-action-pypi-publish@" in content


def test_workflows_use_no_project_and_idempotent_release():
    repo_root = Path(__file__).resolve().parents[1]
    tests_wf = (repo_root / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    release_wf = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    publish_wf = (repo_root / ".github" / "workflows" / "publish-pypi.yml").read_text(
        encoding="utf-8"
    )
    gov_doc = (repo_root / "docs" / "github-governance.md").read_text(encoding="utf-8")

    # Finding #1 & #4: stdlib-only scripts/release.py runs without pre-existing .venv via --no-project
    assert "uv run --no-project python scripts/release.py --check --expect-tag" in release_wf
    assert "uv run --no-project python scripts/release.py --extract-notes" in release_wf
    assert "uv run --no-project python scripts/release.py --check --expect-tag" in publish_wf
    # Finding #2 & #3: no conflicting --generate-notes and idempotent gh release upload
    assert "--generate-notes" not in release_wf
    assert "gh release upload" in release_wf
    # Finding #5: tests.yml isolates concurrency per target ref
    assert "inputs.ref || github.ref" in tests_wf
    # Finding #6: governance doc mentions Trusted Publisher for publish-pypi.yml
    assert "publish-pypi.yml" in gov_doc
