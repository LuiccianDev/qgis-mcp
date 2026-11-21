"""Lookups and conversions shared by every handler group.

Mixed into ``QgisMCPServer`` last, so the domain mixins can rely on these
without importing each other.
"""

import math
import os
import re

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsProject,
)
from qgis.PyQt.QtCore import QTimer, QVariant
from qgis.PyQt.QtWidgets import QApplication

from ..compat import LAYER_RASTER, LAYER_VECTOR
from ..errors import CommandError, LayerNotFound, WrongLayerType


class HandlerBase:
    """Layer lookup and value conversion used by every other mixin."""

    _URI_SECRET_RE = re.compile(
        r"\b(sslpassword|password|pass|pwd)="
        r"('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|\S*)",
        re.IGNORECASE,
    )
    _URI_USERINFO_RE = re.compile(r"(://[^/\s:@]*:)([^/\s?#]+)(@)")

    @classmethod
    def _redact_uri(cls, uri):
        redacted = cls._URI_SECRET_RE.sub(r"\1=***", uri or "")
        return cls._URI_USERINFO_RE.sub(r"\1***\3", redacted)

    @staticmethod
    def _check_safe_filename(value, label="name"):
        """Reject path separators, drive prefixes, NUL bytes, and '.'/'..' segments."""
        if (
            not isinstance(value, str)
            or not value.strip()
            or value in (".", "..")
            or any(c in value for c in ("/", "\\", ":", "\x00"))
            or os.path.isabs(value)
        ):
            raise CommandError(
                f"{label} must be a single file name without path separators or '..'"
            )

    @classmethod
    def _read_project(cls, path):
        """``QgsProject.read(path)``, never blocked on the unavailable-layers dialog.

        When a layer's source is missing, QGIS opens its modal "Handle
        Unavailable Layers" dialog inside read() and waits there for someone to
        close it: over the socket, until the client gives up. The dialog is
        dismissed as soon as it opens, which keeps those layers in the project
        as unavailable (its "Keep Unavailable Layers"), and returns their names
        so the caller can report them.
        """
        timer = QTimer()
        timer.timeout.connect(cls._dismiss_unavailable_layers_dialog)
        timer.start(50)  # fires in the dialog's own event loop
        try:
            project = QgsProject.instance()
            if not project.read(path):
                return False, []
        finally:
            timer.stop()
        return True, [lyr.name() for lyr in project.mapLayers().values() if not lyr.isValid()]

    @staticmethod
    def _dismiss_unavailable_layers_dialog():
        dialog = QApplication.activeModalWidget()
        if dialog is not None and dialog.metaObject().className() == "QgsHandleBadLayers":
            dialog.reject()

    @staticmethod
    def _layer(layer_id):
        """The project layer with *layer_id*, or raise :class:`LayerNotFound`.

        Every handler that takes a ``layer_id`` needs exactly this lookup, and
        it used to be open-coded in a dozen of them: a ``mapLayers()``
        membership test, a raise, and a ``mapLayer()`` call, with the wording of
        the error drifting between sites.
        """
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            raise LayerNotFound(layer_id)
        return layer

    @classmethod
    def _get_vector_layer(cls, layer_id):
        """The layer with *layer_id*, or raise unless it is a vector layer."""
        layer = cls._layer(layer_id)
        if layer.type() != LAYER_VECTOR:
            raise WrongLayerType(f"Not a vector layer: {layer_id}")
        return layer

    @classmethod
    def _get_raster_layer(cls, layer_id):
        """The layer with *layer_id*, or raise unless it is a raster layer."""
        layer = cls._layer(layer_id)
        if layer.type() != LAYER_RASTER:
            raise WrongLayerType(f"Not a raster layer: {layer_id}")
        return layer

    @staticmethod
    def _parse_crs(crs, label="CRS"):
        """The CRS *crs* names, or raise - an invalid one would transform nothing."""
        parsed = QgsCoordinateReferenceSystem(crs)
        if not parsed.isValid():
            raise CommandError(f"Invalid {label}: {crs}")
        return parsed

    def _canvas(self):
        """The active ``QgsMapCanvas``, or raise :class:`CommandError` if unavailable."""
        iface = getattr(self, "iface", None)
        canvas = iface.mapCanvas() if iface is not None else None
        if canvas is None:
            raise CommandError("Map canvas is not available")
        return canvas

    @staticmethod
    def _parse_xy(pt, label="point"):
        """Extract finite ``(x, y)`` floats from ``[x, y]`` or ``{'x': x, 'y': y}``."""
        try:
            if isinstance(pt, dict):
                x, y = float(pt["x"]), float(pt["y"])
            elif isinstance(pt, (list, tuple)) and len(pt) == 2:
                x, y = float(pt[0]), float(pt[1])
            else:
                raise TypeError("expected [x, y] or {'x': x, 'y': y}")
        except (KeyError, TypeError, ValueError) as exc:
            raise CommandError(f"Invalid {label}: {pt!r}") from exc
        if not (math.isfinite(x) and math.isfinite(y)):
            raise CommandError(f"Invalid {label}: coordinates must be finite, got {pt!r}")
        return x, y

    @staticmethod
    def _check_item_keys(item, allowed, required=(), label="Item"):
        """Ensure *item* is a dict with only *allowed* keys and all *required* keys."""
        if not isinstance(item, dict):
            raise CommandError(f"{label}: expected an object, got {type(item).__name__}")
        unknown = sorted(set(item) - set(allowed))
        if unknown:
            expected = " and/or ".join(f"'{k}'" for k in allowed)
            raise CommandError(f"{label}: unknown key(s) {unknown} - expected {expected}")
        for req in required:
            if req not in item:
                raise CommandError(f"{label}: missing '{req}'")

    @staticmethod
    def _load_error(layer):
        """Why *layer* is invalid, as a message suffix ("" when QGIS says nothing).

        GDAL puts the reason on the layer, the virtual provider on its provider
        ("Referenced table x in query not found!"); OGR on neither.
        """
        reasons = [layer.error().summary()]
        provider = layer.dataProvider()
        if provider is not None:
            reasons.append(provider.error().summary())
        reasons = [str(r).strip() for r in dict.fromkeys(reasons) if r and str(r).strip()]
        return f": {'; '.join(reasons)}" if reasons else ""

    @staticmethod
    def _provider_error(provider):
        """A data provider's recorded errors, as a message suffix.

        The list accumulates across calls, so callers clear it before the write
        whose failure this describes.
        """
        errors = [str(e) for e in provider.errors()] if provider.hasErrors() else []
        return f": {'; '.join(errors)}" if errors else ""

    @staticmethod
    def _field_index(layer, field_name, style_type=None):
        """Index of *field_name* on *layer*, or raise :class:`CommandError`."""
        if not field_name:
            msg = f"field is required for {style_type} style" if style_type else "field is required"
            raise CommandError(msg)
        idx = layer.fields().indexOf(field_name)
        if idx < 0:
            raise CommandError(f"Field not found: {field_name}")
        return idx

    @staticmethod
    def _extent_dict(extent):
        """Serialize a ``QgsRectangle`` to ``{xmin, ymin, xmax, ymax}``."""
        return {
            "xmin": extent.xMinimum(),
            "ymin": extent.yMinimum(),
            "xmax": extent.xMaximum(),
            "ymax": extent.yMaximum(),
        }

    @classmethod
    def _provider_mutate(cls, layer, mutate_fn, error_prefix, update_fields=False):
        """Clear provider errors, run ``mutate_fn(dp)``, and raise on falsy return."""
        dp = layer.dataProvider()
        dp.clearErrors()
        result = mutate_fn(dp)
        ok = result[0] if isinstance(result, tuple) else bool(result)
        if not ok:
            raise CommandError(f"{error_prefix}{cls._provider_error(dp)}")
        if update_fields:
            layer.updateFields()
        return result

    def _refresh_layer_symbology(self, layer):
        """Repaint *layer* and refresh its legend node in the layer tree view."""
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())

    @staticmethod
    def _check_filter_expression(layer, expression):
        """Raise unless *expression* parses and prepares against *layer*.

        A filter that fails to parse, or names a field the layer lacks, matches
        nothing without raising - so "0 features" reads as a real answer when
        the filter never ran.
        """
        expr = QgsExpression(expression)
        if expr.hasParserError():
            raise CommandError(f"Expression parse error: {expr.parserErrorString()}")
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        if not expr.prepare(context) or expr.hasEvalError():
            raise CommandError(f"Expression error: {expr.evalErrorString()}")

    @staticmethod
    def _pick(mapping, key, label):
        try:
            return mapping[key]
        except KeyError:
            raise CommandError(f"Unknown {label}: {key!r}. Use one of {sorted(mapping)}") from None

    def _is_visible(self, project, layer_id):
        """Visibility of a layer in the layer tree.

        Non-spatial tables (attribute-only tables, e.g. GeoPackage tables used by QGIS relations)
        live in the project but have no node in the layer tree, so findLayer() returns None.
        Treat them as not visible instead of raising AttributeError.
        """
        node = project.layerTreeRoot().findLayer(layer_id)
        return node.isVisible() if node is not None else False

    def _get_layer_type(self, layer):
        if layer.type() == LAYER_VECTOR:
            return f"vector_{layer.geometryType()}"
        elif layer.type() == LAYER_RASTER:
            return "raster"
        else:
            return str(layer.type())

    def _convert_attribute(self, value):
        """Convert a QVariant / Qt / Python attribute value to a JSON-serializable type.

        PyQGIS hands back Qt date types unwrapped, so the date branch has to run on
        the bare value, not only inside the QVariant case. A value that reaches
        str() unconverted comes out as a PyQt repr, not a date.
        """
        if isinstance(value, QVariant):
            if value.isNull():
                return None
            value = value.value()
        # Tuple form, not `int | float | ...`: PEP 604 unions in isinstance need
        # Python 3.10, and QGIS ships 3.9 well past 3.28 (3.42 still does). The
        # union form raises TypeError there, which broke every feature read.
        if isinstance(value, (int, float, str, bool, type(None))):
            return value
        for to_py in ("toPyDateTime", "toPyDate", "toPyTime"):
            if hasattr(value, to_py):
                value = getattr(value, to_py)()
                break
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
