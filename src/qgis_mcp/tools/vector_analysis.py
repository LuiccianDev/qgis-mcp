"""Vector analysis tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import FieldCalculatorParams


class VectorAnalysisToolset(BaseToolset):
    """MCP toolset for vector attribute calculations, unique values, and spatial joins."""

    domain = "vector_analysis"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Field Calculator",
            description="Add (if missing) + populate a field from a QGIS expression, per feature, in-place. "
            "field_type: string|int|double|bool|date|datetime (default double). "
            "Example: expression='$area', field_name='area'. $area/$length use the project's "
            "ellipsoid and units (reported back as 'measurement'), not necessarily m2/m; the "
            "area()/length() functions are planimetric in the layer CRS (measurement.planimetric_units, "
            "squared for area()); length() of a string counts characters and reports no units. "
            "Returns updated and failed counts; failed features keep their old value and "
            "first_error says why. Refused while the layer has an open edit session.",
        )
        async def field_calculator(
            ctx: Context,
            layer_id: str,
            field_name: str,
            expression: str,
            field_type: str = "double",
            length: int = 0,
            precision: int = 0,
            instance: str | None = None,
        ) -> dict:
            validated = self.validate(
                FieldCalculatorParams,
                layer_id=layer_id,
                field_name=field_name,
                expression=expression,
                field_type=field_type,
                field_length=length,
                field_precision=precision,
            )
            return await _send(
                "field_calculator",
                {
                    "layer_id": validated.layer_id,
                    "field_name": validated.field_name,
                    "expression": validated.expression,
                    "field_type": validated.field_type,
                    "length": validated.field_length,
                    "precision": validated.field_precision,
                },
                instance=instance,
            )

        @mcp.tool(
            title="Get Unique Values",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Return the distinct values of a field. Use 'limit' to cap results "
            "(-1 for all). Useful before building categorized symbology or filters.",
        )
        async def get_unique_values(
            ctx: Context,
            layer_id: str,
            field: str,
            limit: int = 1000,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send(
                "get_unique_values",
                {"layer_id": layer_id, "field": field, "limit": limit},
                instance=instance,
            )

        @mcp.tool(
            title="Spatial Join",
            description="Join attributes by location (native:joinattributesbylocation). "
            "predicates int list: 0=intersects 1=contains 2=equals 3=touches 4=overlaps "
            "5=within 6=crosses (default [0]). method: 0=one-to-many 1=first match (default) "
            "2=largest overlap. First match keeps one arbitrary match per target feature and drops "
            "the others; use 0 when several can match. join_fields = copied columns (default all). "
            "No output_path = in-memory layer. Returns joined_count (target features that found a "
            "match, whatever the method) next to target_features. warnings/warning_count report "
            "features QGIS skipped, e.g. invalid geometries under the Processing setting that skips "
            "them; fix them first (native:fixgeometries) or those features never match.",
        )
        async def spatial_join(
            ctx: Context,
            target_layer: str,
            join_layer: str,
            predicates: list[int] | None = None,
            join_fields: list[str] | None = None,
            method: int = 1,
            prefix: str = "",
            output_path: str | None = None,
            instance: str | None = None,
        ) -> dict:
            await ctx.info("Joining attributes by location...")
            return await _send(
                "spatial_join",
                {
                    "target_layer": target_layer,
                    "join_layer": join_layer,
                    "predicates": predicates,
                    "join_fields": join_fields,
                    "method": method,
                    "prefix": prefix,
                    "output_path": output_path,
                },
                timeout=timeout_long,
                instance=instance,
            )
