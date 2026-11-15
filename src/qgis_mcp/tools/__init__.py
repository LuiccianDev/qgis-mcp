"""Domain MCP toolsets package.

Provides ``ServerContext``, ``BaseToolset``, ``ALL_TOOLSET_CLASSES``,
``build_toolsets()``, and ``register_toolsets()``.
"""

from qgis_mcp.tools import (
    batch,
    canvas,
    code,
    connections,
    connectivity,
    crs,
    debug,
    edit_sessions,
    export,
    expression,
    features,
    features_edit,
    highvalue,
    layer_properties,
    layers,
    layers_visibility,
    layertree,
    layout,
    plugin,
    processing,
    project,
    project_variables,
    raster,
    raster_compute,
    rendering,
    selection,
    session,
    settings,
    symbology,
    vector_analysis,
)
from qgis_mcp.tools.base import BaseToolset, ServerContext
from qgis_mcp.tools.batch import BatchToolset
from qgis_mcp.tools.canvas import CanvasToolset
from qgis_mcp.tools.code import CodeToolset
from qgis_mcp.tools.connections import ConnectionsToolset
from qgis_mcp.tools.connectivity import ConnectivityToolset
from qgis_mcp.tools.crs import CrsToolset
from qgis_mcp.tools.debug import DebugToolset
from qgis_mcp.tools.edit_sessions import EditSessionToolset
from qgis_mcp.tools.export import ExportToolset
from qgis_mcp.tools.expression import ExpressionToolset
from qgis_mcp.tools.features import FeatureToolset
from qgis_mcp.tools.features_edit import FeatureEditToolset
from qgis_mcp.tools.highvalue import HighValueToolset
from qgis_mcp.tools.layer_properties import LayerPropertiesToolset
from qgis_mcp.tools.layers import LayerToolset
from qgis_mcp.tools.layers_visibility import LayerVisibilityToolset
from qgis_mcp.tools.layertree import LayerTreeToolset
from qgis_mcp.tools.layout import LayoutToolset
from qgis_mcp.tools.plugin import PluginToolset
from qgis_mcp.tools.processing import ProcessingToolset
from qgis_mcp.tools.project import ProjectToolset
from qgis_mcp.tools.project_variables import ProjectVariablesToolset
from qgis_mcp.tools.raster import RasterToolset
from qgis_mcp.tools.raster_compute import RasterComputeToolset
from qgis_mcp.tools.rendering import RenderingToolset
from qgis_mcp.tools.selection import SelectionToolset
from qgis_mcp.tools.session import SessionToolset
from qgis_mcp.tools.settings import SettingsToolset
from qgis_mcp.tools.symbology import SymbologyToolset
from qgis_mcp.tools.vector_analysis import VectorAnalysisToolset

ALL_TOOLSET_CLASSES: tuple[type[BaseToolset], ...] = (
    ConnectivityToolset,
    ProjectToolset,
    SessionToolset,
    LayerToolset,
    LayerVisibilityToolset,
    FeatureToolset,
    FeatureEditToolset,
    EditSessionToolset,
    SelectionToolset,
    SymbologyToolset,
    CanvasToolset,
    RasterToolset,
    ProcessingToolset,
    RasterComputeToolset,
    ExportToolset,
    VectorAnalysisToolset,
    RenderingToolset,
    CodeToolset,
    HighValueToolset,
    BatchToolset,
    LayoutToolset,
    DebugToolset,
    PluginToolset,
    LayerTreeToolset,
    LayerPropertiesToolset,
    ProjectVariablesToolset,
    ExpressionToolset,
    SettingsToolset,
    CrsToolset,
    ConnectionsToolset,
)

__all__ = [
    "ALL_TOOLSET_CLASSES",
    "BaseToolset",
    "ServerContext",
    "batch",
    "build_toolsets",
    "canvas",
    "code",
    "connections",
    "connectivity",
    "crs",
    "debug",
    "edit_sessions",
    "export",
    "expression",
    "features",
    "features_edit",
    "highvalue",
    "layer_properties",
    "layers",
    "layers_visibility",
    "layertree",
    "layout",
    "plugin",
    "processing",
    "project",
    "project_variables",
    "raster",
    "raster_compute",
    "register_toolsets",
    "rendering",
    "selection",
    "session",
    "settings",
    "symbology",
    "vector_analysis",
]


def build_toolsets(context: ServerContext) -> list[BaseToolset]:
    """Instantiate all domain toolsets bound to *context*."""
    return [toolset_cls(context) for toolset_cls in ALL_TOOLSET_CLASSES]


def register_toolsets(context: ServerContext) -> list[BaseToolset]:
    """Instantiate and register every domain toolset on ``context.mcp``."""
    toolsets = build_toolsets(context)
    for toolset in toolsets:
        toolset.register()
    return toolsets
