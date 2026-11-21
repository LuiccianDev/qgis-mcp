"""Handlers for layer symbology - vector renderers and raster renderers.

Both handlers are a table of renderer builders plus a common tail (apply the
renderer, repaint, refresh the legend).
"""

from typing import ClassVar

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsClassificationEqualInterval,
    QgsColorRampShader,
    QgsContrastEnhancement,
    QgsGraduatedSymbolRenderer,
    QgsHillshadeRenderer,
    QgsMultiBandColorRenderer,
    QgsRasterShader,
    QgsRectangle,
    QgsRendererCategory,
    QgsSingleBandGrayRenderer,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsStyle,
    QgsSymbol,
)
from qgis.PyQt.QtGui import QColor

from ..compat import (
    CONTRAST_CLIP_MINMAX,
    CONTRAST_NONE,
    CONTRAST_STRETCH_CLIP_MINMAX,
    CONTRAST_STRETCH_MINMAX,
    GRAY_BLACK_TO_WHITE,
    GRAY_WHITE_TO_BLACK,
    SHADER_CLASS_CONTINUOUS,
    SHADER_CLASS_EQUAL_INTERVAL,
    SHADER_CLASS_QUANTILE,
    SHADER_DISCRETE,
    SHADER_EXACT,
    SHADER_INTERPOLATED,
    band_statistics,
)
from ..errors import CommandError
from ..registry import command
from ..wire import zip_strict


class StyleHandlers:
    """Vector and raster symbology."""

    @staticmethod
    def _color_ramp(name):
        """A named ramp from the default style, or raise.

        Falling back to another ramp while the response echoed the requested
        name misreported what was applied.
        """
        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp(name)
        if ramp is None:
            raise CommandError(
                f"Unknown color ramp: {name!r}. Use one of {sorted(style.colorRampNames())}"
            )
        return ramp

    # style_type -> renderer builder. Each builder takes the layer and the
    # styling options and returns a renderer; applying it, repainting and
    # refreshing the legend is common to all three and stays in the handler.
    _VECTOR_STYLES: ClassVar[dict] = {
        "single": "_style_single",
        "categorized": "_style_categorized",
        "graduated": "_style_graduated",
    }

    @staticmethod
    def _apply_symbol_overrides(symbol, color=None, size=None):
        """Apply optional color and marker size / line width to a QgsSymbol."""
        if color is not None:
            qcolor = QColor(color)
            if not qcolor.isValid():
                raise CommandError(f"Invalid color: {color!r}")
            symbol.setColor(qcolor)
        if size is not None:
            size = float(size)
            if size <= 0:
                raise CommandError("size must be positive")
            if hasattr(symbol, "setSize"):
                symbol.setSize(size)
            elif hasattr(symbol, "setWidth"):
                symbol.setWidth(size)

    @classmethod
    def _apply_renderer_overrides(cls, renderer, color=None, size=None):
        """Apply optional color (single symbol) and size/width to a renderer."""
        if hasattr(renderer, "symbol") and renderer.symbol() is not None:
            cls._apply_symbol_overrides(renderer.symbol(), color=color, size=size)
            return
        if hasattr(renderer, "sourceSymbol") and renderer.sourceSymbol() is not None:
            src = renderer.sourceSymbol().clone()
            cls._apply_symbol_overrides(src, size=size)
            renderer.setSourceSymbol(src)
        if hasattr(renderer, "categories"):
            for idx, cat in enumerate(renderer.categories()):
                sym = cat.symbol().clone()
                cls._apply_symbol_overrides(sym, size=size)
                renderer.updateCategorySymbol(idx, sym)

    @staticmethod
    def _style_single(layer, field, classes, color_ramp):
        return QgsSingleSymbolRenderer(QgsSymbol.defaultSymbol(layer.geometryType()))

    @classmethod
    def _style_categorized(cls, layer, field, classes, color_ramp):
        idx = cls._field_index(layer, field, "categorized")
        unique_values = sorted(
            layer.uniqueValues(idx), key=lambda x: str(x) if x is not None else ""
        )
        ramp = cls._color_ramp(color_ramp)

        categories = []
        n = max(len(unique_values) - 1, 1)
        for i, value in enumerate(unique_values):
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(ramp.color(i / n))
            label = str(value) if value is not None else "NULL"
            categories.append(QgsRendererCategory(value, symbol, label))
        return QgsCategorizedSymbolRenderer(field, categories)

    @classmethod
    def _style_graduated(cls, layer, field, classes, color_ramp):
        cls._field_index(layer, field, "graduated")
        renderer = QgsGraduatedSymbolRenderer(field)
        renderer.setSourceSymbol(QgsSymbol.defaultSymbol(layer.geometryType()).clone())
        renderer.setSourceColorRamp(cls._color_ramp(color_ramp))
        renderer.setClassificationMethod(QgsClassificationEqualInterval())
        renderer.updateClasses(layer, classes)
        return renderer

    @command
    def set_layer_style(
        self,
        layer_id,
        style_type,
        field=None,
        classes=5,
        color_ramp="Spectral",
        opacity=1.0,
        color=None,
        size=None,
        **kwargs,
    ):
        opacity = float(opacity)
        if not 0.0 <= opacity <= 1.0:
            raise CommandError("opacity must be between 0.0 and 1.0")
        layer = self._get_vector_layer(layer_id)
        builder = self._pick(self._VECTOR_STYLES, style_type, "style_type")
        renderer = getattr(self, builder)(layer, field, classes, color_ramp)
        if color is not None or size is not None:
            self._apply_renderer_overrides(renderer, color=color, size=size)
        layer.setRenderer(renderer)
        layer.setOpacity(opacity)

        self._refresh_layer_symbology(layer)
        return {"ok": True}

    _SHADER_INTERPOLATION: ClassVar[dict] = {
        "interpolated": SHADER_INTERPOLATED,
        "discrete": SHADER_DISCRETE,
        "exact": SHADER_EXACT,
    }

    _SHADER_CLASSIFICATION: ClassVar[dict] = {
        "continuous": SHADER_CLASS_CONTINUOUS,
        "equal_interval": SHADER_CLASS_EQUAL_INTERVAL,
        "quantile": SHADER_CLASS_QUANTILE,
    }

    _CONTRAST_ALGORITHMS: ClassVar[dict] = {
        "none": CONTRAST_NONE,
        "stretch": CONTRAST_STRETCH_MINMAX,
        "clip": CONTRAST_CLIP_MINMAX,
        "stretch_clip": CONTRAST_STRETCH_CLIP_MINMAX,
    }

    _GRAY_GRADIENTS: ClassVar[dict] = {
        "black_to_white": GRAY_BLACK_TO_WHITE,
        "white_to_black": GRAY_WHITE_TO_BLACK,
    }

    def _band_range(self, provider, band, min_value, max_value):
        """Resolve a band's min/max, falling back to its statistics."""
        if min_value is not None and max_value is not None:
            return float(min_value), float(max_value)
        stats = band_statistics(provider, band)
        lo = stats.minimumValue if min_value is None else float(min_value)
        hi = stats.maximumValue if max_value is None else float(max_value)
        return float(lo), float(hi)

    # style_type -> renderer builder. Each takes the provider, a band-range
    # checker and the styling options, and returns (renderer, applied) - what
    # was actually used, which the response reports back. Applying the renderer
    # and refreshing is common to all four and stays in the handler.
    _RASTER_STYLES: ClassVar[dict] = {
        "singleband_pseudocolor": "_raster_pseudocolor",
        "singleband_gray": "_raster_gray",
        "multiband_color": "_raster_multiband",
        "hillshade": "_raster_hillshade",
    }

    def _contrast_enhancement(self, provider, band, lo, hi, contrast):
        """A configured contrast enhancement - gray and multiband both need one."""
        enhancement = QgsContrastEnhancement(provider.dataType(band))
        enhancement.setContrastEnhancementAlgorithm(
            self._pick(self._CONTRAST_ALGORITHMS, contrast, "contrast")
        )
        enhancement.setMinimumValue(lo)
        enhancement.setMaximumValue(hi)
        return enhancement

    def _raster_pseudocolor(self, provider, check_band, opts):
        band = check_band(opts["band"], "band")
        lo, hi = self._band_range(provider, band, opts["min_value"], opts["max_value"])
        classes = int(opts["classes"])
        shader_fn = QgsColorRampShader(
            lo,
            hi,
            self._color_ramp(opts["color_ramp"]),
            self._pick(self._SHADER_INTERPOLATION, opts["interpolation"], "interpolation"),
            self._pick(self._SHADER_CLASSIFICATION, opts["classification"], "classification"),
        )
        shader_fn.classifyColorRamp(classes, band, QgsRectangle(), provider)
        shader = QgsRasterShader()
        shader.setRasterShaderFunction(shader_fn)
        renderer = QgsSingleBandPseudoColorRenderer(provider, band, shader)
        applied = {
            "band": band,
            "min": lo,
            "max": hi,
            "color_ramp": opts["color_ramp"],
            "classes": classes,
        }
        return renderer, applied

    def _raster_gray(self, provider, check_band, opts):
        band = check_band(opts["band"], "band")
        lo, hi = self._band_range(provider, band, opts["min_value"], opts["max_value"])
        renderer = QgsSingleBandGrayRenderer(provider, band)
        renderer.setGradient(self._pick(self._GRAY_GRADIENTS, opts["gradient"], "gradient"))
        renderer.setContrastEnhancement(
            self._contrast_enhancement(provider, band, lo, hi, opts["contrast"])
        )
        applied = {
            "band": band,
            "min": lo,
            "max": hi,
            "gradient": opts["gradient"],
            "contrast": opts["contrast"],
        }
        return renderer, applied

    def _raster_multiband(self, provider, check_band, opts):
        bands = [
            check_band(opts["red_band"], "red_band"),
            check_band(opts["green_band"], "green_band"),
            check_band(opts["blue_band"], "blue_band"),
        ]
        renderer = QgsMultiBandColorRenderer(provider, *bands)
        setters = (
            renderer.setRedContrastEnhancement,
            renderer.setGreenContrastEnhancement,
            renderer.setBlueContrastEnhancement,
        )
        ranges = []
        for setter, band in zip_strict(setters, bands):
            lo, hi = self._band_range(provider, band, opts["min_value"], opts["max_value"])
            setter(self._contrast_enhancement(provider, band, lo, hi, opts["contrast"]))
            ranges.append({"band": band, "min": lo, "max": hi})
        return renderer, {"bands": ranges, "contrast": opts["contrast"]}

    def _raster_hillshade(self, provider, check_band, opts):
        band = check_band(opts["band"], "band")
        azimuth, altitude = float(opts["azimuth"]), float(opts["altitude"])
        z_factor = float(opts["z_factor"])
        renderer = QgsHillshadeRenderer(provider, band, azimuth, altitude)
        renderer.setZFactor(z_factor)
        applied = {
            "band": band,
            "azimuth": azimuth,
            "altitude": altitude,
            "z_factor": z_factor,
        }
        return renderer, applied

    @command
    def set_raster_style(
        self,
        layer_id,
        style_type,
        band=1,
        color_ramp="Viridis",
        classes=5,
        min_value=None,
        max_value=None,
        classification="continuous",
        interpolation="interpolated",
        gradient="black_to_white",
        contrast="stretch",
        red_band=1,
        green_band=2,
        blue_band=3,
        azimuth=315.0,
        altitude=45.0,
        z_factor=1.0,
        **kwargs,
    ):
        layer = self._get_raster_layer(layer_id)
        provider = layer.dataProvider()
        band_count = provider.bandCount()

        def check_band(b, name):
            b = int(b)
            if not 1 <= b <= band_count:
                raise CommandError(f"{name}={b} out of range (layer has {band_count} band(s))")
            return b

        # The options are a per-style-type union: only a subset means anything to
        # any one renderer, so they travel as a dict rather than 15 arguments
        # threaded through every builder.
        opts = {
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
        }
        builder = self._pick(self._RASTER_STYLES, style_type, "style_type")
        renderer, used = getattr(self, builder)(provider, check_band, opts)

        layer.setRenderer(renderer)
        self._refresh_layer_symbology(layer)
        applied = {"style_type": style_type}
        applied.update(used)
        return {"ok": True, "layer_id": layer.id(), "applied": applied}
