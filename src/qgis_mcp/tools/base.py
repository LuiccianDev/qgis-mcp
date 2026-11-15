"""Shared ServerContext and BaseToolset OOP foundation for MCP domain toolsets."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

try:
    from mcp.server.fastmcp import Context, FastMCP
except ModuleNotFoundError:  # mcp >= 2.0 renamed fastmcp -> mcpserver
    from mcp.server.mcpserver import Context
    from mcp.server.mcpserver import MCPServer as FastMCP

from qgis_mcp.helpers import (
    BATCH_BLOCKED_COMMANDS,
    TIMEOUT_LONG,
    code_failure_message,
    enrich_diagnose,
    make_layer_response,
    make_project_response,
    make_render_response,
)
from qgis_mcp.validation import validate_params

__all__ = ["BaseToolset", "Context", "FastMCP", "ServerContext"]

T = TypeVar("T", bound=BaseModel)


async def _default_confirm_destructive(*_args: Any, **_kwargs: Any) -> bool:
    return True


def _default_cache_as_resource(_data: Any) -> str:
    return ""


def _default_probe_instance(*_args: Any, **_kwargs: Any) -> bool:
    return False


def _default_get_instances() -> dict[str, tuple[str, int]]:
    return {}


def _default_implicit_instance(_instances: Any = None) -> str:
    return "default"


@dataclass
class ServerContext:
    """Shared runtime dependencies injected into every domain Toolset."""

    mcp: Any
    send: Callable[..., Any]
    confirm_destructive: Callable[..., Any] = _default_confirm_destructive
    cache_as_resource: Callable[..., Any] = _default_cache_as_resource
    probe_instance: Callable[..., Any] = _default_probe_instance
    get_instances: Callable[..., Any] = _default_get_instances
    implicit_instance: Callable[..., Any] = _default_implicit_instance
    enrich_diagnose: Callable[..., Any] = enrich_diagnose
    make_layer_response: Callable[..., Any] = make_layer_response
    make_project_response: Callable[..., Any] = make_project_response
    make_render_response: Callable[..., Any] = make_render_response
    timeout_long: float = TIMEOUT_LONG
    batch_blocked_commands: frozenset[str] | set[str] = field(
        default_factory=lambda: BATCH_BLOCKED_COMMANDS
    )
    code_failure_message: Callable[..., str | None] = code_failure_message
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("qgis-mcp"))

    def validate(self, model_cls: type[T], **data: Any) -> T:
        """Validate tool inputs with a Pydantic schema, raising ToolError on failure."""
        return validate_params(model_cls, **data)


class BaseToolset:
    """Object-oriented base class for domain-specific MCP tool collections.

    Each subclass owns one domain (layers, features, processing, etc.), receives
    a shared ``ServerContext`` via composition, and registers its ``@mcp.tool``
    endpoints when ``register()`` is called.
    """

    domain: str = "base"

    def __init__(self, context: ServerContext) -> None:
        self.context = context
        self.mcp = context.mcp
        self._send = context.send
        self._confirm_destructive = context.confirm_destructive
        self._cache_as_resource = context.cache_as_resource

    def validate(self, model_cls: type[T], **data: Any) -> T:
        """Validate arguments through ``ServerContext.validate``."""
        return self.context.validate(model_cls, **data)

    def register(self) -> None:
        """Register all tools belonging to this domain on ``self.mcp``."""
        raise NotImplementedError
