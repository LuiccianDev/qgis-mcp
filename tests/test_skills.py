"""Validate repository Agent Skills under skills/."""

import re
from pathlib import Path

from qgis_mcp.compound_tools import register_compound_tools
from qgis_mcp.helpers import BATCH_BLOCKED_COMMANDS
from qgis_mcp.server import FastMCP, mcp

REPO = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO / "skills"
EXPECTED_SKILLS = ("qgis-mcp-tools", "qgis-mcp-workflows")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter '---'"
    end = text.index("\n---\n", 4)
    raw_meta = text[4:end]
    body = text[end + 5 :]
    meta = {}
    for line in raw_meta.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, body


def _registered_tool_names() -> set[str]:
    granular = {t.name for t in mcp._tool_manager.list_tools()}
    compound_mcp = FastMCP("compound-check")

    async def _noop_send(*_args, **_kwargs):
        return {}

    async def _noop_confirm(*_args, **_kwargs):
        return True

    register_compound_tools(compound_mcp, _noop_send, _noop_confirm)
    compound = {t.name for t in compound_mcp._tool_manager.list_tools()}
    return granular | compound


def test_expected_skills_exist_with_valid_frontmatter():
    for skill_name in EXPECTED_SKILLS:
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_file.is_file(), f"Missing {skill_file}"
        meta, body = _parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        assert meta.get("name") == skill_name
        assert len(meta.get("description", "")) >= 20
        assert len(body.strip()) >= 200


def test_skill_tool_references_match_registered_tools():
    known_tools = _registered_tool_names()
    allowed_non_tools = {
        "qgis_mcp",
        "qgis_listener",
        "instance",
        "action",
        "params",
        "offset",
        "limit",
        "expression",
        "timeout",
        "buffered",
        "connection_mode",
        "load_results",
        "style_type",
        "executed",
        "timed_out",
        "elapsed",
        "endpoint_using_auth_manager",
        "service_using_auth_manager",
        "service_only",
        "granular",
        "compound",
        "stdio",
        "streamable-http",
    } | set(BATCH_BLOCKED_COMMANDS)

    pattern = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
    unknown = []
    for md in SKILLS_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for match in pattern.findall(text):
            if match not in known_tools and match not in allowed_non_tools:
                unknown.append(f"{md.relative_to(REPO)}: `{match}`")
    assert not unknown, f"Unrecognized tool-like identifiers in skills: {unknown}"
