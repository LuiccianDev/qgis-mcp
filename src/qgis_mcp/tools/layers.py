"""Layer Management tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import LayerPaginationParams, MemoryLayerParams


class LayerToolset(BaseToolset):
    """MCP toolset for loading, listing, creating, duplicating, and joining QGIS layers."""

    domain = "layers"

    def _register_core_layer_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive
        make_layer_response = self.context.make_layer_response

        @mcp.tool(
            title="Get Layers",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List layers in the current project with IDs, names, types, visibility, and type-specific info. "
            "Use limit/offset for pagination. Response includes total_count.",
            structured_output=True,
        )
        async def get_layers(
            ctx: Context,
            limit: int = 50,
            offset: int = 0,
            instance: str | None = None,
        ) -> dict[str, Any]:
            validated = self.validate(LayerPaginationParams, limit=limit, offset=offset)
            return await _send(
                "get_layers",
                {"limit": validated.limit, "offset": validated.offset},
                instance=instance,
            )

        @mcp.tool(
            title="Add Vector Layer",
            description="Add a vector layer (shapefile, GeoJSON, GeoPackage, etc.) to the project.",
        )
        async def add_vector_layer(
            ctx: Context,
            path: str,
            provider: str = "ogr",
            name: str | None = None,
            instance: str | None = None,
        ) -> list:
            params = {"path": path, "provider": provider}
            if name:
                params["name"] = name
            result = await _send("add_vector_layer", params, instance=instance)
            return make_layer_response(result)

        @mcp.tool(
            title="Add Raster Layer",
            description="Add a raster layer (GeoTIFF, etc.) to the project.",
        )
        async def add_raster_layer(
            ctx: Context,
            path: str,
            provider: str = "gdal",
            name: str | None = None,
            instance: str | None = None,
        ) -> list:
            params = {"path": path, "provider": provider}
            if name:
                params["name"] = name
            result = await _send("add_raster_layer", params, instance=instance)
            return make_layer_response(result)

        @mcp.tool(
            title="Remove Layer",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Remove a layer from the project by its layer ID. This is irreversible.",
        )
        async def remove_layer(ctx: Context, layer_id: str, instance: str | None = None) -> dict:
            if not await _confirm_destructive(
                ctx, f"Remove layer {layer_id}? This cannot be undone."
            ):
                return {"ok": False, "message": "Cancelled by user"}
            return await _send("remove_layer", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Find Layer",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Find layers by name pattern. Supports fnmatch wildcards (e.g. 'roads*') "
            "and substring matching.",
            structured_output=True,
        )
        async def find_layer(
            ctx: Context,
            name_pattern: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send("find_layer", {"name_pattern": name_pattern}, instance=instance)

        @mcp.tool(
            title="Create Memory Layer",
            description="Create a new in-memory vector layer. geometry_type: Point, LineString, Polygon, "
            "MultiPoint, MultiLineString, MultiPolygon. fields: [{name, type}] where "
            "type is integer, double, string, date, datetime.",
        )
        async def create_memory_layer(
            ctx: Context,
            name: str,
            geometry_type: str,
            crs: str = "EPSG:4326",
            fields: list[dict] | None = None,
            instance: str | None = None,
        ) -> list:
            validated = self.validate(MemoryLayerParams, name=name, geometry_type=geometry_type)
            params: dict[str, Any] = {
                "name": validated.name,
                "geometry_type": validated.geometry_type,
                "crs": crs,
            }
            if fields:
                params["fields"] = fields
            result = await _send("create_memory_layer", params, instance=instance)
            return make_layer_response(result, fallback_name=validated.name)

    def _register_extended_layer_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        make_layer_response = self.context.make_layer_response

        @mcp.tool(
            title="Add Web Layer",
            description="Add a web layer (XYZ, WMS, WFS) to the project. service: 'xyz', 'wms', 'wfs'. "
            "crs is optional and only meaningful for wms ('crs=' in the uri) and wfs ('srsname='): "
            "leave it unset to take whatever the service serves natively. XYZ tiles are always "
            "EPSG:3857, so requesting another CRS for them is an error rather than a silent no-op. "
            "The response reports the CRS the layer actually got.",
        )
        async def add_web_layer(
            ctx: Context,
            url: str,
            service: str,
            name: str | None = None,
            crs: str | None = None,
            instance: str | None = None,
        ) -> list:
            params = {"url": url, "service": service}
            if crs:
                params["crs"] = crs
            if name:
                params["name"] = name
            result = await _send("add_web_layer", params, instance=instance)
            return make_layer_response(result)

        @mcp.tool(
            title="Add Table Join",
            description="Add a table join to a vector layer.",
        )
        async def add_table_join(
            ctx: Context,
            target_layer_id: str,
            join_layer_id: str,
            target_field: str,
            join_field: str,
            prefix: str = "",
            instance: str | None = None,
        ) -> dict:
            params = {
                "target_layer_id": target_layer_id,
                "join_layer_id": join_layer_id,
                "target_field": target_field,
                "join_field": join_field,
                "prefix": prefix,
            }
            return await _send("add_table_join", params, instance=instance)

        @mcp.tool(
            title="Duplicate Layer",
            description="Duplicate a layer (including its style) under a new name.",
        )
        async def duplicate_layer(
            ctx: Context,
            layer_id: str,
            new_name: str | None = None,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "duplicate_layer",
                {"layer_id": layer_id, "new_name": new_name},
                instance=instance,
            )

    def register(self) -> None:
        self._register_core_layer_tools()
        self._register_extended_layer_tools()
