"""Symbology tools."""

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import LayerStyleParams


class SymbologyToolset(BaseToolset):
    """MCP toolset for vector/raster symbology and QML style import/export."""

    domain = "symbology"

    def _register_renderer_tools(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Set Layer Style",
            description="Set symbology. style_type: 'single' (one symbol), 'categorized' (unique values), "
            "'graduated' (numeric ranges). field required for categorized/graduated. "
            "color_ramp: QGIS ramp name (e.g. 'Spectral', 'Viridis', 'Blues'). "
            "classes: graduated class count (default 5). "
            "opacity: layer opacity from 0.0 to 1.0 (default 1.0). "
            "color: optional symbol color (hex like '#ff0000' or color name, for single style). "
            "size: optional marker size or line width (>0).",
        )
        async def set_layer_style(
            ctx: Context,
            layer_id: str,
            style_type: str,
            field: str | None = None,
            classes: int = 5,
            color_ramp: str = "Spectral",
            opacity: float = 1.0,
            color: str | None = None,
            size: float | None = None,
            instance: str | None = None,
        ) -> dict:
            validated = self.validate(
                LayerStyleParams,
                opacity=opacity,
                classes=classes,
                color=color,
                size=size,
            )
            params: dict = {
                "layer_id": layer_id,
                "style_type": style_type,
                "classes": validated.classes,
                "color_ramp": color_ramp,
                "opacity": validated.opacity,
            }
            if field:
                params["field"] = field
            if validated.color is not None:
                params["color"] = validated.color
            if validated.size is not None:
                params["size"] = validated.size
            return await _send("set_layer_style", params, instance=instance)

        @mcp.tool(
            title="Set Raster Style",
            description="Set raster symbology. style_type: 'singleband_pseudocolor' (color ramp over one "
            "band), 'singleband_gray', 'multiband_color' (RGB), 'hillshade'. "
            "min_value/max_value default to the band statistics. "
            "color_ramp: QGIS ramp name (e.g. 'Viridis', 'Spectral', 'RdYlGn'). "
            "classification: continuous|equal_interval|quantile. "
            "interpolation: interpolated|discrete|exact. "
            "gradient (gray): black_to_white|white_to_black. "
            "contrast: none|stretch|clip|stretch_clip. "
            "hillshade uses band, azimuth, altitude, z_factor.",
        )
        async def set_raster_style(
            ctx: Context,
            layer_id: str,
            style_type: str,
            band: int = 1,
            color_ramp: str = "Viridis",
            classes: int = 5,
            min_value: float | None = None,
            max_value: float | None = None,
            classification: str = "continuous",
            interpolation: str = "interpolated",
            gradient: str = "black_to_white",
            contrast: str = "stretch",
            red_band: int = 1,
            green_band: int = 2,
            blue_band: int = 3,
            azimuth: float = 315.0,
            altitude: float = 45.0,
            z_factor: float = 1.0,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "set_raster_style",
                {
                    "layer_id": layer_id,
                    "style_type": style_type,
                    "band": band,
                    "color_ramp": color_ramp,
                    "classes": classes,
                    "min_value": min_value,
                    "max_value": max_value,
                    "classification": classification,
                    "interpolation": interpolation,
                    "gradient": gradient,
                    "contrast": contrast,
                    "red_band": red_band,
                    "green_band": green_band,
                    "blue_band": blue_band,
                    "azimuth": azimuth,
                    "altitude": altitude,
                    "z_factor": z_factor,
                },
                instance=instance,
            )

    def _register_qml_tools(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Apply Style QML",
            description=(
                "Apply a QGIS QML style to a layer, from a file (path) or inline QML text (qml); pass "
                "exactly one. Use it for styles the other styling tools do not model (rule-based "
                "renderers, data-defined properties, SVG fills, blend modes). Rejected, with the "
                "previous style restored, if the XML is malformed, targets the other layer kind, or "
                "QGIS loads a different renderer than the QML declares. Tip: save_style_qml on a "
                "similar layer gives a template in this QGIS version's format."
            ),
        )
        async def apply_style_qml(
            ctx: Context,
            layer_id: str,
            path: str | None = None,
            qml: str | None = None,
            instance: str | None = None,
        ) -> dict:
            params = {"layer_id": layer_id}
            if path is not None:
                params["path"] = path
            if qml is not None:
                params["qml"] = qml
            return await _send("apply_style_qml", params, instance=instance)

        @mcp.tool(
            title="Save Style QML",
            description="Save a layer's style to a QGIS QML file.",
        )
        async def save_style_qml(
            ctx: Context,
            layer_id: str,
            path: str,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "save_style_qml", {"layer_id": layer_id, "path": path}, instance=instance
            )

    def register(self) -> None:
        self._register_renderer_tools()
        self._register_qml_tools()
