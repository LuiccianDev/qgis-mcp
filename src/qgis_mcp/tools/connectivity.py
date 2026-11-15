"""Connectivity and Info tools."""

import asyncio
import os
from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context

_IDENTITY_TIMEOUT = 5  # seconds; listing must stay quick even if one QGIS is busy


async def _no_identity() -> dict[str, Any]:
    """Identity placeholder for an instance that is not reachable."""
    return {}


class ConnectivityToolset(BaseToolset):
    """MCP toolset for ping, diagnostics, multi-instance listing, and metadata."""

    domain = "connectivity"

    async def instance_identity(self, instance: str) -> dict[str, Any]:
        """Resolve runtime identity metadata for a single configured QGIS instance."""
        try:
            info = await self._send(
                "get_qgis_info", timeout=_IDENTITY_TIMEOUT, instance=instance, retries=1
            )
        except Exception:
            return {}

        profile_folder = info.get("profile_folder") or ""
        identity: dict[str, Any] = {
            "qgis_version": info.get("qgis_version"),
            "profile": os.path.basename(profile_folder.replace("\\", "/").rstrip("/")) or None,
            "profile_folder": profile_folder or None,
        }
        for key in ("pid", "window_title"):
            if info.get(key) is not None:
                identity[key] = info[key]
        return {key: value for key, value in identity.items() if value is not None}

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        _probe_instance = self.context.probe_instance
        get_instances = self.context.get_instances
        implicit_instance = self.context.implicit_instance
        enrich_diagnose = self.context.enrich_diagnose
        identity_method = self.instance_identity

        @mcp.tool(
            title="Ping",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Check connectivity to the QGIS plugin server. Returns pong if connected.",
            structured_output=True,
        )
        async def ping(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("ping", instance=instance)

        @mcp.tool(
            title="Diagnose",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Run diagnostic checks on the QGIS MCP stack. Reports QGIS version, "
            "plugin/server version match, processing providers, connected clients, and project status.",
            structured_output=True,
        )
        async def diagnose(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            await ctx.info("Running diagnostics...")
            result = await _send("diagnose", instance=instance)
            return enrich_diagnose(result)

        @mcp.tool(
            title="List QGIS Instances",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List the configured QGIS instances: name, host, port, reachability, and - for "
            "each reachable one - which QGIS actually answered (version, process id, window title, "
            "profile). Use it to confirm a name maps to the window you mean before writing to it. Pass a "
            "name as the 'instance' argument of any other tool to target that QGIS window; omitting it "
            "targets the instance named 'default', or the first one listed when no instance is called "
            "'default'.",
            structured_output=True,
        )
        async def list_qgis_instances(ctx: Context) -> dict[str, Any]:
            instances = get_instances()
            reachable = await asyncio.gather(
                *(
                    asyncio.to_thread(_probe_instance, name, host, port)
                    for name, (host, port) in instances.items()
                )
            )
            import sys

            server_mod = sys.modules.get("qgis_mcp.server")
            identity_fn = getattr(server_mod, "_instance_identity", identity_method)
            identities = await asyncio.gather(
                *(
                    identity_fn(name) if ok else _no_identity()
                    for name, ok in zip(instances, reachable, strict=True)
                )
            )
            entries = []
            for (name, (host, port)), ok, identity in zip(
                instances.items(), reachable, identities, strict=True
            ):
                entry = {"name": name, "host": host, "port": port, "reachable": ok, **identity}
                if ok and not identity:
                    entry["note"] = (
                        "Accepted the connection but did not answer as QGIS: it may be busy, "
                        "or another program holds this port."
                    )
                entries.append(entry)
            return {
                "instances": entries,
                "implicit_instance": implicit_instance(instances),
                "count": len(instances),
            }

        @mcp.tool(
            title="Get QGIS Info",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get QGIS version, profile path, and plugin count.",
            structured_output=True,
        )
        async def get_qgis_info(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_qgis_info", instance=instance)

        @mcp.tool(
            title="Get Project Info",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get current project metadata: filename, title, CRS, layer count, and summary of layers.",
            structured_output=True,
        )
        async def get_project_info(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_project_info", instance=instance)
