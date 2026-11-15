from .plugin import classFactory

# QGIS plugin entry point - re-export via __all__ so ruff sees it used.
__all__ = ["classFactory"]
