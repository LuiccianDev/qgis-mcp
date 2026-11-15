"""Input validation models for MCP tools.

Uses Pydantic to validate common parameters before they reach the plugin,
catching invalid inputs early with clear ToolError messages.
"""

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from qgis_mcp.helpers import ToolError


def validate_params[T: BaseModel](model_cls: type[T], **data: Any) -> T:
    """Validate tool parameters using a Pydantic model, raising ToolError on failure."""
    try:
        return model_cls(**data)
    except ValidationError as exc:
        raise ToolError(str(exc)) from exc


class FeatureQueryParams(BaseModel):
    """Validation for get_layer_features parameters."""

    limit: int = Field(default=10, ge=1, le=50, description="Max features to return (1-50)")
    offset: int = Field(default=0, ge=0, description="Number of features to skip")


class ProcessingParams(BaseModel):
    """Validation for execute_processing and start_processing_job parameters."""

    timeout: int | None = Field(
        default=None,
        ge=1,
        le=600,
        description="Seconds before cancellation (1-600)",
    )


class CoordinatePoint(BaseModel):
    """A single coordinate point."""

    x: float = Field(description="Longitude or easting")
    y: float = Field(description="Latitude or northing")


class CoordinateBbox(BaseModel):
    """A bounding box."""

    xmin: float = Field(description="Minimum x (longitude/easting)")
    ymin: float = Field(description="Minimum y (latitude/northing)")
    xmax: float = Field(description="Maximum x (longitude/easting)")
    ymax: float = Field(description="Maximum y (latitude/northing)")

    @field_validator("xmax", "ymax")
    @classmethod
    def bounds_order(cls, v: float, info) -> float:
        """Allow xmin > xmax for antimeridian-crossing bboxes."""
        return v


class TransformCoordinatesParams(BaseModel):
    """Validation for transform_coordinates parameters."""

    source_crs: str = Field(min_length=1, description="Source CRS (e.g. 'EPSG:4326')")
    target_crs: str = Field(min_length=1, description="Target CRS (e.g. 'EPSG:3857')")
    point: CoordinatePoint | None = None
    points: list[CoordinatePoint] | None = None
    bbox: CoordinateBbox | None = None

    @field_validator("source_crs", "target_crs")
    @classmethod
    def crs_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("CRS string must not be empty")
        return stripped

    @field_validator("points")
    @classmethod
    def points_not_empty(cls, v: list[CoordinatePoint] | None) -> list[CoordinatePoint] | None:
        if v is not None and len(v) == 0:
            raise ValueError("points list must not be empty")
        return v


class RenderMapParams(BaseModel):
    """Validation for render_map parameters."""

    width: int = Field(default=800, ge=1, le=10000, description="Image width in pixels")
    height: int = Field(default=600, ge=1, le=10000, description="Image height in pixels")


class CanvasExtentParams(BaseModel):
    """Validation for set_canvas_extent parameters (bbox)."""

    xmin: float = Field(description="Minimum x")
    ymin: float = Field(description="Minimum y")
    xmax: float = Field(description="Maximum x")
    ymax: float = Field(description="Maximum y")


class CanvasScaleParams(BaseModel):
    """Validation for set_canvas_scale parameters."""

    scale: float = Field(gt=0, le=100000000, description="Map scale denominator")


class PostgreSQLConnectionParams(BaseModel):
    """Validation for create_postgresql_connection parameters."""

    name: str = Field(min_length=1, max_length=255, description="Connection name")
    port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Database port (1-65535)",
    )
    ssl_mode: str = Field(
        default="prefer",
        description="SSL mode: prefer, disable, allow, require, verify-ca, verify-full",
    )

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("connection name must not be empty")
        return stripped

    @field_validator("ssl_mode")
    @classmethod
    def ssl_mode_valid(cls, v: str) -> str:
        allowed = {"prefer", "disable", "allow", "require", "verify-ca", "verify-full"}
        if v not in allowed:
            raise ValueError(f"ssl_mode must be one of: {', '.join(sorted(allowed))}")
        return v


class MemoryLayerParams(BaseModel):
    """Validation for create_memory_layer parameters."""

    name: str = Field(min_length=1, description="Layer name")
    geometry_type: str = Field(
        default="POINT",
        description="Geometry type: NONE, POINT, LINESTRING, POLYGON, etc.",
    )

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("layer name must not be empty")
        return stripped


class FieldCalculatorParams(BaseModel):
    """Validation for field_calculator parameters."""

    layer_id: str = Field(min_length=1, description="Target layer ID")
    expression: str = Field(min_length=1, description="QGIS expression")
    field_name: str | None = Field(default=None, description="New field name (for new fields)")
    field_type: str = Field(default="double", description="Field type: double, int, string, bool")
    field_length: int = Field(default=0, ge=0, description="Field length for string fields")
    field_precision: int = Field(default=-1, ge=-1, description="Field precision for double fields")

    @field_validator("field_type")
    @classmethod
    def field_type_valid(cls, v: str) -> str:
        allowed = {"double", "int", "string", "bool", "date", "datetime", "time"}
        if v not in allowed:
            raise ValueError(f"field_type must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("expression")
    @classmethod
    def expression_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("expression must not be empty")
        return stripped


class LayerPaginationParams(BaseModel):
    """Validation for paginated layer listing parameters."""

    limit: int = Field(default=50, ge=1, le=500, description="Max layers to return (1-500)")
    offset: int = Field(default=0, ge=0, description="Number of layers to skip")


class LayerStyleParams(BaseModel):
    """Validation for set_layer_style parameters."""

    opacity: float | None = Field(default=None, ge=0.0, le=1.0, description="Layer opacity (0-1)")
    classes: int = Field(default=5, ge=1, le=100, description="Graduated class count (1-100)")
    color: str | None = Field(
        default=None,
        min_length=1,
        description="Optional symbol color (hex like '#ff0000' or CSS color name)",
    )
    size: float | None = Field(
        default=None,
        gt=0.0,
        le=500.0,
        description="Optional marker size or line width (>0)",
    )

    @field_validator("color")
    @classmethod
    def color_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("color must not be empty")
        return stripped


class LayoutExportParams(BaseModel):
    """Validation for export_layout parameters."""

    layout_name: str = Field(min_length=1, description="Print layout name")
    path: str = Field(min_length=1, description="Destination file path")
    dpi: int = Field(default=300, ge=10, le=3000, description="Export resolution in DPI")


class Screenshot3DParams(BaseModel):
    """Validation for get_3d_screenshot parameters."""

    view_index: int = Field(default=0, ge=0, description="3D map view index")
    dpi: int = Field(default=96, ge=10, le=600, description="Render resolution in DPI")
    pitch: float | None = Field(
        default=None, ge=-90.0, le=90.0, description="Optional camera pitch in degrees"
    )
    distance: float | None = Field(
        default=None, gt=0, description="Optional camera distance in metres"
    )
    heading: float | None = Field(
        default=None, ge=0.0, le=360.0, description="Optional camera heading in degrees"
    )


class UndoRedoParams(BaseModel):
    """Validation for undo_edits and redo_edits parameters."""

    layer_id: str = Field(min_length=1, description="Target vector layer ID")
    steps: int = Field(default=1, ge=1, le=1000, description="Number of edit steps (1-1000)")


class MessageLogParams(BaseModel):
    """Validation for get_message_log parameters."""

    limit: int = Field(default=100, ge=1, le=1000, description="Max log entries (1-1000)")


class BatchCommandItem(BaseModel):
    """Validation for a single command item inside batch_commands."""

    type: str = Field(min_length=1, description="QGIS command name")
    params: dict[str, Any] = Field(default_factory=dict, description="Command arguments")


class LayoutGridParams(BaseModel):
    """Validation for add_layout_grid parameters."""

    layout_name: str = Field(min_length=1, description="Print layout name")
    map_item_id: str | None = Field(default=None, description="Target map item UUID")
    interval_x: float = Field(default=1.0, gt=0.0, description="X grid interval (>0)")
    interval_y: float = Field(default=1.0, gt=0.0, description="Y grid interval (>0)")
    name: str = Field(default="Grid", min_length=1, description="Grid name")
    show_annotations: bool = Field(default=True, description="Show coordinate annotations")
    crs: str | None = Field(default=None, description="Optional grid CRS (e.g. 'EPSG:4326')")


class UpdateLayoutItemParams(BaseModel):
    """Validation for update_layout_item parameters."""

    layout_name: str = Field(min_length=1, description="Print layout name")
    item_id: str = Field(min_length=1, description="Layout item UUID or ID")
    x: float | None = Field(default=None, description="New X position (mm)")
    y: float | None = Field(default=None, description="New Y position (mm)")
    width: float | None = Field(default=None, gt=0.0, description="New width (mm)")
    height: float | None = Field(default=None, gt=0.0, description="New height (mm)")
    text: str | None = Field(default=None, description="New text (for label items)")
    visible: bool | None = Field(default=None, description="Item visibility")


class RemoveLayoutItemParams(BaseModel):
    """Validation for remove_layout_item parameters."""

    layout_name: str = Field(min_length=1, description="Print layout name")
    item_id: str = Field(min_length=1, description="Layout item UUID or ID")
