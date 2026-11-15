"""Handlers for the map canvas: extent, scale, rendering and screenshots."""

import base64
import contextlib
import os
import secrets
import tempfile

from qgis.core import (
    QgsCoordinateTransform,
    QgsLayoutExporter,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
    QgsVectorSimplifyMethod,
)
from qgis.PyQt.QtCore import QBuffer, QByteArray, QEventLoop, QSize, QTimer
from qgis.PyQt.QtGui import QColor, QImage

from ..compat import IODEVICE_WRITEONLY, LAYOUT_SUCCESS, SIMPLIFY_ANTIALIAS, SIMPLIFY_GEOMETRY
from ..errors import CommandError
from ..registry import command


class CanvasHandlers:
    """Map canvas extent, scale, rendering and screenshots."""

    @command
    def get_canvas_extent(self, **kwargs):
        canvas = self._canvas()
        extent = canvas.extent()
        crs = canvas.mapSettings().destinationCrs()
        return {
            **self._extent_dict(extent),
            "crs": crs.authid(),
            "width": canvas.width(),
            "height": canvas.height(),
        }

    @command
    def set_canvas_extent(self, xmin, ymin, xmax, ymax, crs=None, **kwargs):
        canvas = self._canvas()
        rect = QgsRectangle(xmin, ymin, xmax, ymax)
        dst_crs = canvas.mapSettings().destinationCrs()
        response = {}

        if crs:
            # An invalid CRS makes an invalid transform, which returns the box
            # unchanged: degrees were applied as map units without a word.
            src_crs = self._parse_crs(crs)
            if src_crs != dst_crs:
                transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
                crossing = transform.transformBoundingBox(rect, handle180Crossover=True)
                rect = transform.transformBoundingBox(rect)
                if crossing.xMinimum() > crossing.xMaximum():
                    # One canvas extent cannot wrap; it spans the long way round.
                    response["warning"] = (
                        "The box crosses the antimeridian; the canvas extent spans "
                        "the full longitude range between its edges instead."
                    )

        canvas.setExtent(rect)
        canvas.refresh()
        response["extent"] = [rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()]
        response["crs"] = dst_crs.authid()
        return response

    _RENDER_TIMEOUT = 55  # seconds (below MCP's 60s TIMEOUT_LONG)

    @staticmethod
    def _clone_canvas_map_settings(canvas, width, height):
        """Clone live canvas settings with target output dimensions and simplification."""
        # Clone the canvas settings so the render reproduces what the user
        # sees: visible layers only, canvas/custom draw order, destination
        # CRS, transform context, labeling, style overrides and temporal
        # state. Rebuilding from the project registry
        # (QgsProject.mapLayers()) renders hidden layers in registry order
        # and can place an opaque hidden layer over the overlays (issue #21).
        src = canvas.mapSettings()
        try:
            ms = QgsMapSettings(src)  # copy constructor (preferred)
        except Exception:
            # Fallback if the copy constructor is unavailable on this QGIS:
            # at minimum honour visibility, draw order, CRS and transform.
            ms = QgsMapSettings()
            ms.setLayers(src.layers())
            ms.setDestinationCrs(src.destinationCrs())
            ms.setTransformContext(QgsProject.instance().transformContext())
        ms.setExtent(canvas.extent())
        ms.setOutputSize(QSize(width, height))
        ms.setBackgroundColor(QColor(255, 255, 255))
        ms.setOutputDpi(96)

        # Enable geometry simplification (matches QGIS canvas defaults).
        # Skips sub-pixel vertices - critical for large datasets at small scales.
        simplify = QgsVectorSimplifyMethod()
        simplify.setSimplifyHints(SIMPLIFY_GEOMETRY | SIMPLIFY_ANTIALIAS)
        simplify.setThreshold(1.0)  # 1 pixel
        simplify.setForceLocalOptimization(True)
        ms.setSimplifyMethod(simplify)
        return ms

    @staticmethod
    def _encode_png_base64(image_or_pixmap, error_label):
        """Encode a ``QImage`` or ``QPixmap`` to a base64 PNG string."""
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(IODEVICE_WRITEONLY)
        if not image_or_pixmap.save(buf, "PNG"):
            raise CommandError(f"Failed to encode {error_label} as PNG")
        buf.close()
        return base64.b64encode(bytes(ba)).decode("ascii")

    @command
    def render_map_base64(self, width=800, height=600, path=None, **kwargs):
        """Render the map and return base64-encoded PNG data."""
        try:
            canvas = self._canvas()
            ms = self._clone_canvas_map_settings(canvas, width, height)
            render = QgsMapRendererParallelJob(ms)

            # Use QEventLoop + QTimer for non-blocking wait with timeout.
            # Keeps Qt event loop alive and allows cancellation.
            loop = QEventLoop()
            timed_out = []
            finished = []
            render.finished.connect(lambda: finished.append(True))
            render.finished.connect(loop.quit)

            timeout_timer = QTimer()
            timeout_timer.setSingleShot(True)
            timeout_timer.timeout.connect(lambda: (timed_out.append(True), loop.quit()))
            timeout_timer.start(self._RENDER_TIMEOUT * 1000)

            render.start()
            # A trivial project can finish inside start(); quit() on a loop that
            # is not running yet is a no-op, so exec() would wait for the timeout.
            if not finished:
                loop.exec()

            timeout_timer.stop()
            if timed_out:
                render.cancelWithoutBlocking()
                render.waitForFinished()
                raise CommandError(f"Render timed out after {self._RENDER_TIMEOUT}s")

            img = render.renderedImage()
            if path and not img.save(path):
                raise CommandError(f"Failed to write image to {path}")

            b64 = self._encode_png_base64(img, "the rendered map")
            response = {
                "base64_data": b64,
                "mime_type": "image/png",
                "width": width,
                "height": height,
            }
            # A layer that failed to draw (broken WMS, moved file) leaves a blank
            # area in an image that otherwise looks like a successful render.
            errors = [f"{e.layerID}: {e.message}" for e in render.errors()]
            if errors:
                response["warnings"] = errors
            return response

        except CommandError:
            raise  # the render timeout above - don't re-wrap a deliberate message
        except Exception as e:
            raise CommandError(f"Render error: {e!s}") from e

    @command
    def get_canvas_screenshot(self, **kwargs):
        """Grab the current map canvas as a fast screenshot (no re-render)."""
        canvas = self._canvas()
        pixmap = canvas.grab()
        b64 = self._encode_png_base64(pixmap, "the canvas grab")
        return {
            "base64_data": b64,
            "mime_type": "image/png",
            "width": pixmap.width(),
            "height": pixmap.height(),
        }

    @staticmethod
    def _export_3d_layout_png(map_settings, pose, page_w, page_h, dpi):
        """Render a cloned 3D map scene through a temporary print layout to PNG bytes."""
        from qgis._3d import QgsLayoutItem3DMap

        layout = QgsPrintLayout(QgsProject.instance())
        tmp = os.path.join(tempfile.gettempdir(), f"mcp_3d_{secrets.token_hex(6)}.png")
        try:
            layout.initializeDefaults()
            layout.pageCollection().page(0).setPageSize(QgsLayoutSize(page_w, page_h))

            item = QgsLayoutItem3DMap(layout)
            item.attemptMove(QgsLayoutPoint(0, 0))
            item.attemptResize(QgsLayoutSize(page_w, page_h))
            item.setMapSettings(map_settings)
            item.setCameraPose(pose)
            layout.addLayoutItem(item)

            exporter = QgsLayoutExporter(layout)
            export_settings = QgsLayoutExporter.ImageExportSettings()
            export_settings.dpi = dpi
            result = exporter.exportToImage(tmp, export_settings)
            if int(result) != int(LAYOUT_SUCCESS) or not os.path.exists(tmp):
                reason = exporter.errorMessage()
                detail = f": {reason}" if reason else ""
                raise CommandError(f"3D layout export failed (export code {int(result)}){detail}")
            with open(tmp, "rb") as fh:
                return fh.read()
        finally:
            layout.deleteLater()
            with contextlib.suppress(Exception):
                os.remove(tmp)

    @command
    def get_3d_screenshot(
        self, view_index=0, dpi=96, pitch=None, distance=None, heading=None, **kwargs
    ):
        """Capture an open 3D Map View as a PNG image.

        The 3D map view is an OpenGL ``QWindow`` that ``QWidget.grab()`` cannot
        read, so this reuses the open view's scene settings + camera pose and
        renders them through a print layout's 3D map item (whose offscreen 3D
        engine runs in C++). Requires a 3D map view to be open
        (View > 3D Map Views > New 3D Map View).

        Optional ``pitch`` (0 = straight down / top-down, 90 = horizontal /
        edge-on; ~45 is a balanced oblique), ``heading`` (compass degrees), and
        ``distance`` (metres) override the captured camera angle without changing
        the live view.
        """
        view_index = int(view_index)
        dpi = max(10, min(int(dpi), 600))  # clamp: bound render cost / memory use
        try:
            from qgis._3d import Qgs3DMapSettings
        except ImportError as e:
            raise CommandError(
                f"3D support is unavailable in this QGIS build (qgis._3d import failed: {e})"
            ) from e

        views = self.iface.mapCanvases3D()
        if not views:
            raise CommandError(
                "No 3D map view is open. Open one via "
                "View > 3D Map Views > New 3D Map View, frame your scene, then retry."
            )
        if view_index < 0 or view_index >= len(views):
            raise CommandError(
                f"view_index {view_index} out of range (open 3D views: {len(views)})"
            )
        canvas3d = views[view_index]

        # Clone the scene settings (copy constructor) so the live view is never
        # mutated or shared, and snapshot its current camera pose.
        map_settings = Qgs3DMapSettings(canvas3d.mapSettings())
        pose = canvas3d.cameraController().cameraPose()

        # Optional camera overrides - applied only to this captured copy, so the
        # live 3D view is left untouched.
        if pitch is not None:
            pose.setPitchAngle(max(0.0, min(float(pitch), 90.0)))
        if heading is not None:
            pose.setHeadingAngle(float(heading) % 360.0)
        if distance is not None and float(distance) > 0:
            pose.setDistanceFromCenterPoint(float(distance))

        # Match the output image to the 3D view's aspect ratio.
        size = canvas3d.size()
        view_w = max(1, size.width())
        view_h = max(1, size.height())
        page_w = 200.0
        page_h = page_w * view_h / view_w
        data = self._export_3d_layout_png(map_settings, pose, page_w, page_h, dpi)

        img = QImage()
        img.loadFromData(data, "PNG")
        return {
            "base64_data": base64.b64encode(data).decode("ascii"),
            "mime_type": "image/png",
            "width": img.width(),
            "height": img.height(),
            "view_index": view_index,
            "open_3d_views": len(views),
        }

    @command
    def transform_coordinates(
        self, source_crs, target_crs, point=None, points=None, bbox=None, **kwargs
    ):
        """Transform coordinates between coordinate reference systems."""
        src = self._parse_crs(source_crs, "source CRS")
        dst = self._parse_crs(target_crs, "target CRS")

        xform = QgsCoordinateTransform(src, dst, QgsProject.instance())
        result = {"source_crs": source_crs, "target_crs": target_crs}

        if point is not None:
            x, y = self._parse_xy(point, "point")
            pt = xform.transform(QgsPointXY(x, y))
            result["point"] = {"x": pt.x(), "y": pt.y()}

        if points is not None:
            if not isinstance(points, list):
                raise CommandError("points must be a list")
            transformed = []
            for p in points:
                x, y = self._parse_xy(p, "point")
                pt = xform.transform(QgsPointXY(x, y))
                transformed.append({"x": pt.x(), "y": pt.y()})
            result["points"] = transformed

        if bbox:
            rect = QgsRectangle(bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"])
            # Without the crossover handling a box spanning 180 deg came back
            # spanning the other ~350 deg of longitude. With it, a crossing box
            # comes back with xmin > xmax, which is flagged rather than hidden.
            transformed_rect = xform.transformBoundingBox(rect, handle180Crossover=True)
            result["bbox"] = self._extent_dict(transformed_rect)
            result["crosses_antimeridian"] = (
                transformed_rect.xMinimum() > transformed_rect.xMaximum()
            )

        return result

    @command
    def get_canvas_scale(self, **kwargs):
        """Get map canvas scale, rotation, and magnification."""
        canvas = self._canvas()
        return {
            "scale": canvas.scale(),
            "rotation": canvas.rotation(),
            "magnification": canvas.magnificationFactor(),
        }

    @command
    def set_canvas_scale(self, scale=None, rotation=None, **kwargs):
        """Set map canvas scale and/or rotation."""
        canvas = self._canvas()
        if scale is not None:
            canvas.zoomScale(scale)
        if rotation is not None:
            canvas.setRotation(rotation)
        canvas.refresh()
        return {
            "ok": True,
            "scale": canvas.scale(),
            "rotation": canvas.rotation(),
        }
