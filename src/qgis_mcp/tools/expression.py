"""Expression Validation tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class ExpressionToolset(BaseToolset):
    """MCP toolset for validating and evaluating QGIS expressions."""

    domain = "expression"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Validate Expression",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Validate a QGIS expression. Returns whether it's valid, any parse errors, "
            "and referenced column names. Optionally test against a layer's fields.",
            structured_output=True,
        )
        async def validate_expression(
            ctx: Context,
            expression: str,
            layer_id: str | None = None,
            instance: str | None = None,
        ) -> dict[str, Any]:
            params = {"expression": expression}
            if layer_id:
                params["layer_id"] = layer_id
            return await _send("validate_expression", params, instance=instance)

        @mcp.tool(
            title="Evaluate Expression",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Evaluate a standalone QGIS expression to a scalar value (e.g. "
            "aggregate('layer','sum','field'), @project_var, now()). Optional layer_id adds layer "
            "scope. Distinct from validate_expression (validate only) and field_calculator (per-feature).",
        )
        async def evaluate_expression(
            ctx: Context,
            expression: str,
            layer_id: str | None = None,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "evaluate_expression",
                {"expression": expression, "layer_id": layer_id},
                instance=instance,
            )
