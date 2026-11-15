"""Tests for input validation models in validation.py.

Verifies that invalid inputs are rejected with clear error messages
before they reach the plugin.
"""

import pytest
from pydantic import ValidationError

from qgis_mcp.helpers import ToolError
from qgis_mcp.validation import (
    BatchCommandItem,
    CanvasScaleParams,
    CoordinateBbox,
    CoordinatePoint,
    FeatureQueryParams,
    FieldCalculatorParams,
    LayerPaginationParams,
    LayerStyleParams,
    LayoutExportParams,
    MemoryLayerParams,
    MessageLogParams,
    PostgreSQLConnectionParams,
    ProcessingParams,
    RenderMapParams,
    Screenshot3DParams,
    TransformCoordinatesParams,
    UndoRedoParams,
    validate_params,
)


class TestFeatureQueryParams:
    """Tests for get_layer_features parameter validation."""

    def test_default_values(self):
        """Default limit=10, offset=0 should be valid."""
        params = FeatureQueryParams()
        assert params.limit == 10
        assert params.offset == 0

    def test_valid_range(self):
        """Values within range should be accepted."""
        params = FeatureQueryParams(limit=50, offset=100)
        assert params.limit == 50
        assert params.offset == 100

    def test_limit_zero_rejected(self):
        """limit=0 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureQueryParams(limit=0)
        assert (
            "greater than or equal to 1" in str(exc_info.value).lower()
            or "ge=1" in str(exc_info.value).lower()
            or "greater than" in str(exc_info.value).lower()
        )

    def test_limit_negative_rejected(self):
        """Negative limit should be rejected."""
        with pytest.raises(ValidationError):
            FeatureQueryParams(limit=-1)

    def test_limit_too_high_rejected(self):
        """limit > 50 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureQueryParams(limit=51)
        assert "50" in str(exc_info.value)

    def test_limit_way_too_high_rejected(self):
        """limit=200 should be rejected with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureQueryParams(limit=200)
        error_str = str(exc_info.value)
        assert "50" in error_str

    def test_offset_negative_rejected(self):
        """Negative offset should be rejected."""
        with pytest.raises(ValidationError):
            FeatureQueryParams(offset=-1)


class TestProcessingParams:
    """Tests for execute_processing parameter validation."""

    def test_no_timeout_is_valid(self):
        """None timeout should be accepted."""
        params = ProcessingParams()
        assert params.timeout is None

    def test_valid_timeout(self):
        """Timeout within range should be accepted."""
        params = ProcessingParams(timeout=55)
        assert params.timeout == 55

    def test_timeout_zero_rejected(self):
        """timeout=0 should be rejected."""
        with pytest.raises(ValidationError):
            ProcessingParams(timeout=0)

    def test_timeout_negative_rejected(self):
        """Negative timeout should be rejected."""
        with pytest.raises(ValidationError):
            ProcessingParams(timeout=-10)

    def test_timeout_too_high_rejected(self):
        """timeout > 600 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessingParams(timeout=601)
        assert "600" in str(exc_info.value)

    def test_timeout_way_too_high_rejected(self):
        """timeout=3600 should be rejected."""
        with pytest.raises(ValidationError):
            ProcessingParams(timeout=3600)


class TestCoordinatePoint:
    """Tests for coordinate point validation."""

    def test_valid_point(self):
        """Valid coordinates should be accepted."""
        point = CoordinatePoint(x=10.5, y=48.2)
        assert point.x == 10.5
        assert point.y == 48.2

    def test_negative_coordinates(self):
        """Negative coordinates (south/west) should be accepted."""
        point = CoordinatePoint(x=-74.0, y=-33.5)
        assert point.x == -74.0
        assert point.y == -33.5

    def test_missing_x_rejected(self):
        """Missing x should be rejected."""
        with pytest.raises(ValidationError):
            CoordinatePoint(y=48.2)

    def test_missing_y_rejected(self):
        """Missing y should be rejected."""
        with pytest.raises(ValidationError):
            CoordinatePoint(x=10.5)


class TestCoordinateBbox:
    """Tests for bounding box validation."""

    def test_valid_bbox(self):
        """Valid bbox should be accepted."""
        bbox = CoordinateBbox(xmin=0, ymin=0, xmax=10, ymax=10)
        assert bbox.xmin == 0
        assert bbox.xmax == 10

    def test_antimeridian_bbox(self):
        """xmin > xmax (antimeridian crossing) should be allowed."""
        bbox = CoordinateBbox(xmin=170, ymin=-10, xmax=-170, ymax=10)
        assert bbox.xmin == 170
        assert bbox.xmax == -170


class TestTransformCoordinatesParams:
    """Tests for transform_coordinates parameter validation."""

    def test_valid_point_transform(self):
        """Valid point transform should be accepted."""
        params = TransformCoordinatesParams(
            source_crs="EPSG:4326",
            target_crs="EPSG:3857",
            point={"x": 10.5, "y": 48.2},
        )
        assert params.source_crs == "EPSG:4326"

    def test_valid_points_transform(self):
        """Valid points list should be accepted."""
        params = TransformCoordinatesParams(
            source_crs="EPSG:4326",
            target_crs="EPSG:3857",
            points=[{"x": 10.5, "y": 48.2}, {"x": 11.0, "y": 49.0}],
        )
        assert len(params.points) == 2

    def test_valid_bbox_transform(self):
        """Valid bbox should be accepted."""
        params = TransformCoordinatesParams(
            source_crs="EPSG:4326",
            target_crs="EPSG:3857",
            bbox={"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10},
        )
        assert params.bbox.xmin == 0

    def test_empty_source_crs_rejected(self):
        """Empty source_crs should be rejected."""
        with pytest.raises(ValidationError):
            TransformCoordinatesParams(
                source_crs="", target_crs="EPSG:3857", point={"x": 0, "y": 0}
            )

    def test_empty_target_crs_rejected(self):
        """Empty target_crs should be rejected."""
        with pytest.raises(ValidationError):
            TransformCoordinatesParams(
                source_crs="EPSG:4326", target_crs="", point={"x": 0, "y": 0}
            )

    def test_whitespace_only_crs_rejected(self):
        """Whitespace-only CRS should be rejected."""
        with pytest.raises(ValidationError):
            TransformCoordinatesParams(
                source_crs="   ", target_crs="EPSG:3857", point={"x": 0, "y": 0}
            )

    def test_empty_points_list_rejected(self):
        """Empty points list should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TransformCoordinatesParams(source_crs="EPSG:4326", target_crs="EPSG:3857", points=[])
        assert "empty" in str(exc_info.value).lower()

    def test_crs_stripped(self):
        """CRS with whitespace should be stripped."""
        params = TransformCoordinatesParams(
            source_crs="  EPSG:4326  ",
            target_crs="EPSG:3857",
            point={"x": 0, "y": 0},
        )
        assert params.source_crs == "EPSG:4326"


class TestRenderMapParams:
    """Tests for render_map parameter validation."""

    def test_default_dimensions(self):
        """Default width=800, height=600 should be valid."""
        params = RenderMapParams()
        assert params.width == 800
        assert params.height == 600

    def test_valid_dimensions(self):
        """Valid dimensions should be accepted."""
        params = RenderMapParams(width=1920, height=1080)
        assert params.width == 1920

    def test_zero_width_rejected(self):
        """width=0 should be rejected."""
        with pytest.raises(ValidationError):
            RenderMapParams(width=0)

    def test_too_large_dimension_rejected(self):
        """Dimensions > 10000 should be rejected."""
        with pytest.raises(ValidationError):
            RenderMapParams(width=10001)


class TestCanvasScaleParams:
    """Tests for set_canvas_scale parameter validation."""

    def test_valid_scale(self):
        """Valid scale should be accepted."""
        params = CanvasScaleParams(scale=10000)
        assert params.scale == 10000

    def test_zero_scale_rejected(self):
        """scale=0 should be rejected."""
        with pytest.raises(ValidationError):
            CanvasScaleParams(scale=0)

    def test_negative_scale_rejected(self):
        """Negative scale should be rejected."""
        with pytest.raises(ValidationError):
            CanvasScaleParams(scale=-100)

    def test_too_large_scale_rejected(self):
        """Scale > 100,000,000 should be rejected."""
        with pytest.raises(ValidationError):
            CanvasScaleParams(scale=100000001)


class TestPostgreSQLConnectionParams:
    """Tests for create_postgresql_connection parameter validation."""

    def test_valid_connection(self):
        """Valid connection params should be accepted."""
        params = PostgreSQLConnectionParams(name="mydb")
        assert params.name == "mydb"

    def test_valid_port(self):
        """Valid port should be accepted."""
        params = PostgreSQLConnectionParams(name="mydb", port=5432)
        assert params.port == 5432

    def test_port_zero_rejected(self):
        """port=0 should be rejected."""
        with pytest.raises(ValidationError):
            PostgreSQLConnectionParams(name="mydb", port=0)

    def test_port_too_high_rejected(self):
        """port > 65535 should be rejected."""
        with pytest.raises(ValidationError):
            PostgreSQLConnectionParams(name="mydb", port=65536)

    def test_invalid_ssl_mode_rejected(self):
        """Invalid ssl_mode should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PostgreSQLConnectionParams(name="mydb", ssl_mode="invalid")
        assert "ssl_mode" in str(exc_info.value).lower()

    def test_valid_ssl_modes(self):
        """All valid ssl_modes should be accepted."""
        for mode in ("prefer", "disable", "allow", "require", "verify-ca", "verify-full"):
            params = PostgreSQLConnectionParams(name="mydb", ssl_mode=mode)
            assert params.ssl_mode == mode

    def test_empty_name_rejected(self):
        """Empty name should be rejected."""
        with pytest.raises(ValidationError):
            PostgreSQLConnectionParams(name="")

    def test_whitespace_name_stripped(self):
        """Whitespace-only name should be rejected after strip."""
        with pytest.raises(ValidationError):
            PostgreSQLConnectionParams(name="   ")


class TestMemoryLayerParams:
    """Tests for create_memory_layer parameter validation."""

    def test_valid_layer(self):
        """Valid layer params should be accepted."""
        params = MemoryLayerParams(name="test_layer")
        assert params.name == "test_layer"
        assert params.geometry_type == "POINT"

    def test_empty_name_rejected(self):
        """Empty name should be rejected."""
        with pytest.raises(ValidationError):
            MemoryLayerParams(name="")

    def test_name_stripped(self):
        """Name with whitespace should be stripped."""
        params = MemoryLayerParams(name="  my_layer  ")
        assert params.name == "my_layer"


class TestFieldCalculatorParams:
    """Tests for field_calculator parameter validation."""

    def test_valid_params(self):
        """Valid params should be accepted."""
        params = FieldCalculatorParams(layer_id="layer_1", expression='"field" * 2')
        assert params.layer_id == "layer_1"
        assert params.field_type == "double"

    def test_invalid_field_type_rejected(self):
        """Invalid field_type should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FieldCalculatorParams(layer_id="layer_1", expression="1", field_type="invalid")
        assert "field_type" in str(exc_info.value).lower()

    def test_valid_field_types(self):
        """All valid field_types should be accepted."""
        for ftype in ("double", "int", "string", "date", "datetime", "time"):
            params = FieldCalculatorParams(layer_id="layer_1", expression="1", field_type=ftype)
            assert params.field_type == ftype

    def test_empty_expression_rejected(self):
        """Empty expression should be rejected."""
        with pytest.raises(ValidationError):
            FieldCalculatorParams(layer_id="layer_1", expression="")

    def test_whitespace_expression_rejected(self):
        """Whitespace-only expression should be rejected."""
        with pytest.raises(ValidationError):
            FieldCalculatorParams(layer_id="layer_1", expression="   ")

    def test_expression_stripped(self):
        """Expression with whitespace should be stripped."""
        params = FieldCalculatorParams(layer_id="layer_1", expression='  "field" * 2  ')
        assert params.expression == '"field" * 2'

    def test_empty_layer_id_rejected(self):
        """Empty layer_id should be rejected."""
        with pytest.raises(ValidationError):
            FieldCalculatorParams(layer_id="", expression="1")


class TestExtendedValidationModels:
    """Tests for validate_params helper and extended domain models."""

    def test_validate_params_converts_validation_error_to_tool_error(self):
        validated = validate_params(FeatureQueryParams, limit=25, offset=5)
        assert validated.limit == 25
        with pytest.raises(ToolError, match="less than or equal to 50"):
            validate_params(FeatureQueryParams, limit=99)

    def test_layer_pagination_params(self):
        assert LayerPaginationParams().limit == 50
        with pytest.raises(ValidationError):
            LayerPaginationParams(limit=0)
        with pytest.raises(ValidationError):
            LayerPaginationParams(offset=-1)

    def test_layer_style_params(self):
        params = LayerStyleParams(opacity=0.5, classes=7, color="#ff0000", size=4.5)
        assert params.opacity == 0.5
        assert params.classes == 7
        assert params.color == "#ff0000"
        assert params.size == 4.5
        with pytest.raises(ValidationError):
            LayerStyleParams(opacity=1.5)
        with pytest.raises(ValidationError):
            LayerStyleParams(classes=0)
        with pytest.raises(ValidationError):
            LayerStyleParams(color="   ")
        with pytest.raises(ValidationError):
            LayerStyleParams(size=0)

    def test_layout_export_params(self):
        params = LayoutExportParams(layout_name="Map1", path="/tmp/out.pdf", dpi=300)
        assert params.dpi == 300
        with pytest.raises(ValidationError):
            LayoutExportParams(layout_name="", path="/tmp/out.pdf")
        with pytest.raises(ValidationError):
            LayoutExportParams(layout_name="Map1", path="/tmp/out.pdf", dpi=5)

    def test_screenshot_3d_params(self):
        params = Screenshot3DParams(view_index=0, dpi=150)
        assert params.dpi == 150
        with pytest.raises(ValidationError):
            Screenshot3DParams(view_index=-1)
        with pytest.raises(ValidationError):
            Screenshot3DParams(dpi=900)

    def test_undo_redo_params(self):
        assert UndoRedoParams(layer_id="lyr").steps == 1
        with pytest.raises(ValidationError):
            UndoRedoParams(layer_id="lyr", steps=0)

    def test_message_log_params(self):
        assert MessageLogParams().limit == 100
        with pytest.raises(ValidationError):
            MessageLogParams(limit=0)

    def test_batch_command_item(self):
        item = BatchCommandItem(type="ping", params={})
        assert item.type == "ping"
        with pytest.raises(ValidationError):
            BatchCommandItem(type="")

    def test_layout_grid_and_item_params(self):
        from qgis_mcp.validation import (
            LayoutGridParams,
            RemoveLayoutItemParams,
            UpdateLayoutItemParams,
        )

        grid = LayoutGridParams(layout_name="Map1", interval_x=2.0, interval_y=2.0)
        assert grid.interval_x == 2.0
        with pytest.raises(ValidationError):
            LayoutGridParams(layout_name="Map1", interval_x=0)

        upd = UpdateLayoutItemParams(layout_name="Map1", item_id="abc", x=10, width=50)
        assert upd.width == 50
        with pytest.raises(ValidationError):
            UpdateLayoutItemParams(layout_name="Map1", item_id="abc", width=-5)

        rem = RemoveLayoutItemParams(layout_name="Map1", item_id="abc")
        assert rem.item_id == "abc"
        with pytest.raises(ValidationError):
            RemoveLayoutItemParams(layout_name="Map1", item_id="")

    def test_screenshot_3d_camera_params(self):
        p = Screenshot3DParams(view_index=0, dpi=150, pitch=45.0, distance=500.0, heading=180.0)
        assert p.pitch == 45.0
        assert p.distance == 500.0
        assert p.heading == 180.0
        with pytest.raises(ValidationError):
            Screenshot3DParams(distance=-1)
        with pytest.raises(ValidationError):
            Screenshot3DParams(pitch=95.0)
        with pytest.raises(ValidationError):
            Screenshot3DParams(heading=400.0)
