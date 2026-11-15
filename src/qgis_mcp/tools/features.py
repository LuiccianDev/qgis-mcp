"""Feature Access tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import FeatureQueryParams


class FeatureToolset(BaseToolset):
    """MCP toolset for querying vector features, statistics, SQL, and feature identification."""

    domain = "features"

    def _register_feature_read_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        _cache_as_resource = self._cache_as_resource

        @mcp.tool(
            title="Get Layer Features",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get features from a vector layer. Flat dicts: _fid + attributes at top level. "
            "expression filter (QGIS, e.g. "
            '"name = \'Berlin\'", "population > 1000000"), limit (max 50, larger is refused; default 10), offset for paging, '
            "optional geometry in _geometry key. feature_count is the layer total; matched is the "
            "count after the expression filter.",
            structured_output=True,
        )
        async def get_layer_features(
            ctx: Context,
            layer_id: str,
            limit: int = 10,
            offset: int = 0,
            expression: str | None = None,
            include_geometry: bool = False,
            instance: str | None = None,
        ) -> dict[str, Any]:
            validated = self.validate(FeatureQueryParams, limit=limit, offset=offset)
            params: dict[str, Any] = {
                "layer_id": layer_id,
                "limit": validated.limit,
                "offset": validated.offset,
                "include_geometry": include_geometry,
            }
            if expression:
                params["expression"] = expression
            result = await _send("get_layer_features", params, instance=instance)

            if len(result.get("features", [])) > 20:
                uri = _cache_as_resource(result["features"])
                result["features_resource"] = uri
                result["_hint"] = (
                    f"Result contains many features. You can also access them via {uri}"
                )

            return result

        @mcp.tool(
            title="Get Field Statistics",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Compute aggregate statistics (count, sum, mean, min, max, stdev) for a numeric field. "
            "For non-numeric fields returns count and distinct values.",
            structured_output=True,
        )
        async def get_field_statistics(
            ctx: Context,
            layer_id: str,
            field_name: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send(
                "get_field_statistics",
                {"layer_id": layer_id, "field_name": field_name},
                instance=instance,
            )

    def _register_sql_and_identify_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Execute SQL",
            description="SQL across loaded layers via a virtual layer; reference layers by name in "
            "FROM/JOIN. as_layer=True registers the result as a new layer (set geometry_field for "
            "spatial output); else returns rows inline, capped by limit (default 1000, negative for all) "
            "with a truncated flag. layers limits sources by layer id.",
        )
        async def execute_sql(
            ctx: Context,
            query: str,
            layers: list[str] | None = None,
            as_layer: bool = False,
            layer_name: str = "sql_result",
            geometry_field: str | None = None,
            uid_field: str | None = None,
            limit: int = 1000,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "execute_sql",
                {
                    "query": query,
                    "layers": layers,
                    "as_layer": as_layer,
                    "layer_name": layer_name,
                    "geometry_field": geometry_field,
                    "uid_field": uid_field,
                    "limit": limit,
                },
                timeout=timeout_long,
                instance=instance,
            )

        @mcp.tool(
            title="Identify Features",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Identify features at a point [x, y] across layers (map-click analogue). "
            "The point and tolerance are in crs when given, else the project CRS; layers in another "
            "CRS are reprojected. tolerance (in those units) expands the search; 0 = exact hit. "
            "layer_ids limits the search (default: visible vector layers). limit caps features per "
            "layer. Layers the point cannot be transformed into are listed in skipped_layers.",
        )
        async def identify_features(
            ctx: Context,
            point: list[float],
            tolerance: float = 0.0,
            layer_ids: list[str] | None = None,
            limit: int = 10,
            crs: str | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {
                "point": point,
                "tolerance": tolerance,
                "layer_ids": layer_ids,
                "limit": limit,
            }
            if crs:
                params["crs"] = crs
            return await _send("identify_features", params, instance=instance)

    def register(self) -> None:
        self._register_feature_read_tools()
        self._register_sql_and_identify_tools()
