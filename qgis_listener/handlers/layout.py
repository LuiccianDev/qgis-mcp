"""Handlers for print layouts, layout items and atlas export."""

import os
from typing import ClassVar

from qgis.core import (
    QgsLayoutExporter,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
)
from qgis.PyQt.QtGui import QColor

from ..compat import LAYOUT_SUCCESS, RENDER_UNIT_POINTS
from ..errors import CommandError
from ..registry import command


class LayoutHandlers:
    """Print layouts, layout items and atlas export."""

    @command
    def list_layouts(self, **kwargs):
        manager = QgsProject.instance().layoutManager()
        layouts = []
        for layout in manager.layouts():
            layouts.append(
                {
                    "name": layout.name(),
                    "page_count": layout.pageCollection().pageCount(),
                }
            )
        return {"layouts": layouts, "count": len(layouts)}

    # format -> (QgsLayoutExporter settings class, exporter method). Named
    # rather than referenced so the attribute lookup happens on the running
    # QGIS, as elsewhere in the plugin; the accepted list is the table's keys.
    _LAYOUT_EXPORTS: ClassVar[dict] = dict(
        {"pdf": ("PdfExportSettings", "exportToPdf"), "svg": ("SvgExportSettings", "exportToSvg")},
        **dict.fromkeys(
            ("png", "jpg", "jpeg", "tif", "tiff", "bmp"),
            ("ImageExportSettings", "exportToImage"),
        ),
    )

    @command
    def export_layout(self, layout_name, path, format="pdf", dpi=300, **kwargs):
        layout = self._get_layout(layout_name)
        exporter = QgsLayoutExporter(layout)
        settings_name, method = self._pick(self._LAYOUT_EXPORTS, format.lower(), "format")
        settings = getattr(QgsLayoutExporter, settings_name)()
        settings.dpi = dpi
        result = getattr(exporter, method)(path, settings)

        if result != LAYOUT_SUCCESS:
            reason = exporter.errorMessage()
            detail = f": {reason}" if reason else ""
            raise CommandError(f"Export failed with code: {result}{detail}")

        return {"ok": True, "path": path}

    _ORIENTATIONS: ClassVar[dict] = {
        "landscape": "Landscape",
        "portrait": "Portrait",
    }

    @command
    def create_layout(self, name, page_size="A4", orientation="landscape", **kwargs):
        """Create a new print layout."""
        orient_attr = self._pick(self._ORIENTATIONS, orientation.lower(), "orientation")
        orient_enum = getattr(QgsLayoutItemPage, "Orientation", QgsLayoutItemPage)
        orient = getattr(orient_enum, orient_attr)

        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        try:
            layout.initializeDefaults()
            page = layout.pageCollection().page(0)
            if page is not None and not page.setPageSize(page_size, orient):
                raise CommandError(f"Invalid page_size: {page_size!r}")
            layout.setName(name)
            # addLayout refuses a duplicate name; ignoring that sent every later
            # item call to the existing layout of that name.
            if not project.layoutManager().addLayout(layout):
                raise CommandError(
                    f"Could not add layout '{name}' (a layout with that name exists?)"
                )
        except Exception:
            layout.deleteLater()
            raise
        return {"ok": True, "name": name}

    @command
    def add_layout_map(self, layout_name, x, y, width, height, extent=None, scale=None, **kwargs):
        """Add a map item to a print layout."""
        if extent is not None:
            if not isinstance(extent, (list, tuple)) or len(extent) != 4:
                raise CommandError("extent must be [xmin, ymin, xmax, ymax]")
            xmin, ymin, xmax, ymax = (float(v) for v in extent)
            if xmin >= xmax or ymin >= ymax:
                raise CommandError("extent must satisfy xmin < xmax and ymin < ymax")
        if scale is not None:
            scale = float(scale)
            if scale <= 0:
                raise CommandError("scale must be positive")

        layout = self._get_layout(layout_name)
        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(x, y))
        map_item.attemptResize(QgsLayoutSize(width, height))
        target_extent = (
            QgsRectangle(xmin, ymin, xmax, ymax)
            if extent is not None
            else self.iface.mapCanvas().extent()
        )
        map_item.zoomToExtent(target_extent)
        if scale is not None:
            map_item.setScale(scale)
        layout.addLayoutItem(map_item)
        return {"ok": True}

    def _get_layout(self, layout_name):
        """Get a print layout by name or raise."""
        layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
        if not layout:
            raise CommandError(f"Layout not found: {layout_name}")
        return layout

    def _find_layout_map(self, layout, map_item_id=None):
        """The map item with id/uuid *map_item_id*, else the first map item.

        An explicit id that matches nothing raises: falling back to the first
        map linked the legend or scale bar to a map the caller did not name.
        """
        maps = [it for it in layout.items() if isinstance(it, QgsLayoutItemMap)]
        if map_item_id:
            for m in maps:
                if m.id() == map_item_id or m.uuid() == map_item_id:
                    return m
            raise CommandError(f"Map item not found in layout: {map_item_id}")
        return maps[0] if maps else None

    @command
    def get_layout_info(self, layout_name, **kwargs):
        """List items in a print layout (type, id, position, size)."""
        layout = self._get_layout(layout_name)
        items = []
        for item in layout.items():
            if not hasattr(item, "uuid"):
                continue
            try:
                pos = item.positionWithUnits()
                size = item.sizeWithUnits()
                x, y = pos.x(), pos.y()
                w, h = size.width(), size.height()
            except Exception:
                x = y = w = h = None
            items.append(
                {
                    "id": item.id(),
                    "uuid": item.uuid(),
                    "type": type(item).__name__,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                }
            )
        return {
            "layout": layout_name,
            "items": items,
            "count": len(items),
            "page_count": layout.pageCollection().pageCount(),
        }

    @staticmethod
    def _style_label(label, color, font_size):
        """Set a layout label's colour and size through the current API.

        QGIS 4 deprecates setFontColor()/font()/setFont() on QgsLayoutItemLabel
        in favour of a QgsTextFormat, and each call logs a DeprecationWarning
        with a traceback into the user's QGIS log. setTextFormat() arrived in
        3.24, below the plugin's 3.28 minimum, but the old path is kept as a
        fallback rather than assuming: a missing method here would take out
        every layout label.
        """
        text_format = getattr(label, "textFormat", None)
        if text_format is not None and hasattr(label, "setTextFormat"):
            fmt = text_format()
            fmt.setColor(QColor(color))
            fmt.setSize(float(font_size))
            fmt.setSizeUnit(RENDER_UNIT_POINTS)
            label.setTextFormat(fmt)
            return
        label.setFontColor(QColor(color))
        font = label.font()
        font.setPointSize(int(font_size))
        label.setFont(font)

    @command
    def add_layout_label(
        self,
        layout_name,
        text,
        x=10,
        y=10,
        width=100,
        height=20,
        font_size=12,
        color="#000000",
        **kwargs,
    ):
        """Add a text label to a print layout. Supports [% expression %] in text."""
        from qgis.core import QgsLayoutItemLabel

        layout = self._get_layout(layout_name)
        label = QgsLayoutItemLabel(layout)
        label.setText(text)
        self._style_label(label, color, font_size)
        layout.addLayoutItem(label)
        label.attemptMove(QgsLayoutPoint(x, y))
        label.attemptResize(QgsLayoutSize(width, height))
        return {"ok": True, "uuid": label.uuid()}

    @command
    def add_layout_legend(
        self,
        layout_name,
        map_item_id=None,
        x=10,
        y=10,
        width=80,
        height=100,
        title="Legend",
        layer_ids=None,
        **kwargs,
    ):
        """Add a legend to a print layout, linked to a map item."""
        layers = [self._layer(lid) for lid in layer_ids] if layer_ids is not None else None
        layout = self._get_layout(layout_name)
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle(title)
        map_item = self._find_layout_map(layout, map_item_id)
        if map_item:
            legend.setLinkedMap(map_item)
        if layers is not None:
            legend.setAutoUpdateModel(False)
            root = legend.model().rootGroup()
            root.removeAllChildren()
            for layer in layers:
                root.addLayer(layer)
        layout.addLayoutItem(legend)
        legend.attemptMove(QgsLayoutPoint(x, y))
        legend.attemptResize(QgsLayoutSize(width, height))
        return {"ok": True, "uuid": legend.uuid()}

    @command
    def add_layout_scalebar(
        self,
        layout_name,
        map_item_id=None,
        x=10,
        y=180,
        width=80,
        height=20,
        style="Single Box",
        **kwargs,
    ):
        """Add a scale bar to a print layout, linked to a map item."""
        from qgis.core import QgsLayoutItemScaleBar

        layout = self._get_layout(layout_name)
        bar = QgsLayoutItemScaleBar(layout)
        bar.setStyle(style)
        map_item = self._find_layout_map(layout, map_item_id)
        if map_item:
            bar.setLinkedMap(map_item)
        bar.applyDefaultSize()
        layout.addLayoutItem(bar)
        bar.attemptMove(QgsLayoutPoint(x, y))
        bar.attemptResize(QgsLayoutSize(width, height))
        return {"ok": True, "uuid": bar.uuid()}

    @command
    def add_layout_picture(self, layout_name, path, x=10, y=10, width=30, height=30, **kwargs):
        """Add a picture/SVG (logo, north arrow) to a print layout."""
        from qgis.core import QgsLayoutItemPicture

        layout = self._get_layout(layout_name)
        pic = QgsLayoutItemPicture(layout)
        pic.setPicturePath(path)
        layout.addLayoutItem(pic)
        pic.attemptMove(QgsLayoutPoint(x, y))
        pic.attemptResize(QgsLayoutSize(width, height))
        return {"ok": True, "uuid": pic.uuid()}

    @command
    def add_layout_table(
        self,
        layout_name,
        layer_id,
        x=10,
        y=10,
        width=180,
        height=80,
        max_rows=20,
        **kwargs,
    ):
        """Add an attribute table for a vector layer to a print layout."""
        from qgis.core import QgsLayoutFrame, QgsLayoutItemAttributeTable

        layer = self._get_vector_layer(layer_id)
        layout = self._get_layout(layout_name)
        table = QgsLayoutItemAttributeTable.create(layout)
        table.setVectorLayer(layer)
        table.setMaximumNumberOfFeatures(int(max_rows))
        layout.addMultiFrame(table)
        frame = QgsLayoutFrame(layout, table)
        frame.attemptMove(QgsLayoutPoint(x, y))
        frame.attemptResize(QgsLayoutSize(width, height))
        table.addFrame(frame)
        return {"ok": True, "uuid": frame.uuid()}

    @command
    def configure_atlas(
        self,
        layout_name,
        coverage_layer,
        enabled=True,
        page_name_expression=None,
        filter_expression=None,
        sort_expression=None,
        **kwargs,
    ):
        """Configure the atlas of a print layout (coverage layer, filter, sort)."""
        layer = self._get_vector_layer(coverage_layer)
        layout = self._get_layout(layout_name)
        atlas = layout.atlas()
        atlas.setEnabled(bool(enabled))
        atlas.setCoverageLayer(layer)
        if page_name_expression:
            atlas.setPageNameExpression(page_name_expression)
        if filter_expression:
            atlas.setFilterFeatures(True)
            # Returns (ok, error); a syntax error otherwise left count 0 and ok.
            ok, error = atlas.setFilterExpression(filter_expression)
            if not ok:
                raise CommandError(f"Atlas filter expression error: {error}")
        if sort_expression:
            atlas.setSortFeatures(True)
            atlas.setSortExpression(sort_expression)
        atlas.updateFeatures()
        return {
            "ok": True,
            "coverage_layer": layer.name(),
            "enabled": bool(enabled),
            "count": atlas.count(),
        }

    @command
    def export_atlas(self, layout_name, output_path, format="pdf", dpi=300, **kwargs):
        """Export an atlas: single multi-page PDF, or one image file per feature."""

        layout = self._get_layout(layout_name)
        atlas = layout.atlas()
        if not atlas.enabled():
            raise CommandError("Atlas not enabled; call configure_atlas first")
        atlas.updateFeatures()
        fmt = format.lower()
        if fmt == "pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            settings.dpi = dpi
            result, error = QgsLayoutExporter.exportToPdf(atlas, output_path, settings)
        elif fmt in ("png", "jpg", "jpeg", "tif", "tiff"):
            os.makedirs(output_path, exist_ok=True)
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = dpi
            base = os.path.join(output_path, layout_name)
            result, error = QgsLayoutExporter.exportToImage(atlas, base, fmt, settings)
        else:
            raise CommandError(f"Unsupported atlas format: {format}")
        if result != LAYOUT_SUCCESS:
            raise CommandError(f"Atlas export failed: {error}")
        return {"ok": True, "output": output_path, "count": atlas.count()}

    @command
    def remove_layout(self, layout_name, **kwargs):
        """Remove a print layout from the project."""
        layout = self._get_layout(layout_name)
        QgsProject.instance().layoutManager().removeLayout(layout)
        return {"ok": True, "removed": layout_name}

    @staticmethod
    def _find_layout_item(layout, item_id):
        """Find a layout item by UUID or user-assigned ID."""
        item = layout.itemByUuid(item_id)
        if item is not None:
            return item
        for candidate in layout.items():
            if candidate.id() == item_id:
                return candidate
        raise CommandError(f"Layout item not found: {item_id}")

    @command
    def add_layout_grid(
        self,
        layout_name,
        map_item_id=None,
        interval_x=1.0,
        interval_y=1.0,
        name="Grid",
        show_annotations=True,
        crs=None,
        **kwargs,
    ):
        """Add a coordinate grid to a map item in a print layout."""
        from qgis.core import QgsLayoutItemMapGrid

        layout = self._get_layout(layout_name)
        map_item = self._find_layout_map(layout, map_item_id)
        if map_item is None:
            raise CommandError(f"No map item found in layout '{layout_name}'")
        grid = QgsLayoutItemMapGrid(name, map_item)
        grid.setIntervalX(float(interval_x))
        grid.setIntervalY(float(interval_y))
        grid.setAnnotationEnabled(bool(show_annotations))
        if crs:
            grid.setCrs(self._parse_crs(crs))
        map_item.grids().addGrid(grid)
        map_item.updateBoundingRect()
        layout.refresh()
        return {"ok": True, "name": name, "map_item_id": map_item.uuid()}

    @command
    def update_layout_item(
        self,
        layout_name,
        item_id,
        x=None,
        y=None,
        width=None,
        height=None,
        text=None,
        visible=None,
        **kwargs,
    ):
        """Update position, size, text, or visibility of an existing layout item."""
        layout = self._get_layout(layout_name)
        item = self._find_layout_item(layout, item_id)
        if x is not None or y is not None:
            pos = item.positionWithUnits()
            item.attemptMove(
                QgsLayoutPoint(
                    pos.x() if x is None else float(x), pos.y() if y is None else float(y)
                )
            )
        if width is not None or height is not None:
            sz = item.sizeWithUnits()
            item.attemptResize(
                QgsLayoutSize(
                    sz.width() if width is None else float(width),
                    sz.height() if height is None else float(height),
                )
            )
        if text is not None:
            if not hasattr(item, "setText"):
                raise CommandError(f"Layout item '{item_id}' does not support text updates")
            item.setText(text)
        if visible is not None:
            item.setVisibility(bool(visible))
        layout.refresh()
        return {"ok": True, "uuid": item.uuid()}

    @command
    def remove_layout_item(self, layout_name, item_id, **kwargs):
        """Remove an item from a print layout by UUID or ID."""
        layout = self._get_layout(layout_name)
        item = self._find_layout_item(layout, item_id)
        layout.removeLayoutItem(item)
        layout.refresh()
        return {"ok": True, "removed": item_id}
