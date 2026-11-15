"""Batch tools."""

from typing import Any

from qgis_mcp.helpers import ToolError
from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import BatchCommandItem


class BatchToolset(BaseToolset):
    """MCP toolset for executing validated command batches."""

    domain = "batch"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        blocked_commands = self.context.batch_blocked_commands

        @mcp.tool(
            title="Batch Commands",
            description="Execute multiple commands in a single round-trip. Each command is "
            '{"type": "<command_name>", "params": {...}}. Destructive commands '
            f"({', '.join(sorted(blocked_commands))}) "
            "are not allowed in batch, call them individually.",
        )
        async def batch_commands(
            ctx: Context, commands: list[dict], instance: str | None = None
        ) -> list[dict[str, Any]]:
            for cmd in commands:
                if not isinstance(cmd, dict):
                    raise ToolError(f"Each command must be an object, got {type(cmd).__name__}")
                cmd_type = cmd.get("type", "")
                if cmd_type in blocked_commands:
                    raise ToolError(
                        f"Command {cmd_type!r} is not allowed in batch, "
                        "call it individually so confirmation can be requested"
                    )
                self.validate(BatchCommandItem, **cmd)
            return await _send("batch", {"commands": commands}, instance=instance)
