"""QGIS MCP.

Exposes QGIS Desktop as Model Context Protocol tools.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qgis-mcp")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
