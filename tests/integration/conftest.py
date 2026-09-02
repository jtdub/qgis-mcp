"""Fixtures that run the QGIS MCP plugin inside a headless QGIS.

These tests need a Python that can import qgis.core. Run them with the Python
that ships inside QGIS, or inside the qgis/qgis container. Without QGIS the
whole directory collects nothing.
"""

import os
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
"""The checkout. It holds qgis_mcp_plugin, and src holds the qgis_mcp package."""

for _import_root in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))


def _point_proj_at_its_database():
    """Tell PROJ where its database is, when the environment does not.

    A macOS QGIS bundle keeps proj.db inside the application. Without this,
    every CRS resolves to nothing and the coordinate tests fail for the wrong
    reason. A Linux install needs no help.
    """
    if os.environ.get("PROJ_LIB") or os.environ.get("PROJ_DATA"):
        return
    for candidate in Path("/Applications").glob("QGIS*.app/Contents/Resources/proj"):
        if (candidate / "proj.db").exists():
            os.environ["PROJ_LIB"] = str(candidate)
            os.environ["PROJ_DATA"] = str(candidate)
            return


_point_proj_at_its_database()

try:
    import qgis.core  # noqa: F401

    QGIS_IS_AVAILABLE = True
except ImportError:  # pragma: no cover
    QGIS_IS_AVAILABLE = False

collect_ignore_glob = [] if QGIS_IS_AVAILABLE else ["test_*.py"]

TOKEN = "integration-token"
"""Token every request in this suite carries."""


def free_port():
    """Return a TCP port that nothing listens on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="session")
def qgis_app():
    """Start QGIS once, without a window."""
    from qgis.testing import start_app

    return start_app()


@pytest.fixture(scope="session")
def iface(qgis_app):
    """Return the stand-in for the QGIS Desktop interface.

    Its mapCanvas() is a real QgsMapCanvas. The rest is a mock.
    """
    from qgis.testing.mocked import get_iface

    return get_iface()


@pytest.fixture(autouse=True)
def empty_project(qgis_app, iface):
    """Give each test an empty project and an empty canvas."""
    from qgis.core import QgsProject

    QgsProject.instance().clear()
    iface.mapCanvas().setLayers([])
    yield
    QgsProject.instance().clear()


@pytest.fixture
def plugin(iface):
    """Return a plugin server that is not listening on a socket."""
    from qgis_mcp_plugin.qgis_mcp_plugin import QgisMCPServer

    return QgisMCPServer(iface=iface, token=TOKEN)


def add_layer(layer):
    """Add a layer to the project and return it."""
    from qgis.core import QgsProject

    QgsProject.instance().addMapLayer(layer)
    return layer


def build_layer(definition, name, rows, crs="EPSG:4326"):
    """Return a memory layer holding the given rows.

    Args:
        definition: The geometry keyword, such as Point or LineString.
        name: The layer name.
        rows: Pairs of (WKT geometry or None, list of attribute values).
        crs: The CRS authority id.
    """
    from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer

    layer = QgsVectorLayer(f"{definition}&crs={crs}", name, "memory")
    assert layer.isValid(), f"Could not build the memory layer '{name}'"

    features = []
    for wkt, attributes in rows:
        feature = QgsFeature(layer.fields())
        feature.setAttributes(list(attributes))
        if wkt is not None:
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
        features.append(feature)

    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    return layer


@pytest.fixture
def cities():
    """A point layer with a name, a population, and one NULL name."""
    rows = [
        ("POINT(-71.97 -13.53)", ["Cusco", 430000]),
        ("POINT(-77.04 -12.05)", ["Lima", 9700000]),
        ("POINT(-71.53 -16.40)", ["Arequipa", 1000000]),
        ("POINT(-69.18 -15.84)", ["Puno", 140000]),
        ("POINT(-70.02 -15.50)", [None, 5000]),
    ]
    return add_layer(build_layer("Point?field=name:string(40)&field=pop:integer", "cities", rows))


@pytest.fixture
def rivers():
    """A river network whose NEXT_DOWN pointers run to the sea."""
    rows = [
        ("LINESTRING(-72.0 -13.5, -72.1 -13.6)", [10, 20, 1, "Vilcanota"]),
        ("LINESTRING(-72.1 -13.6, -72.2 -13.7)", [20, 30, 2, "Vilcanota"]),
        ("LINESTRING(-72.2 -13.7, -72.3 -13.8)", [30, 40, 3, "Urubamba"]),
        ("LINESTRING(-72.3 -13.8, -72.4 -13.9)", [40, 0, 4, "Urubamba"]),
        ("LINESTRING(-70.0 -15.0, -70.1 -15.1)", [90, 0, 1, "Ramis"]),
    ]
    definition = (
        "LineString?field=HYRIV_ID:integer&field=NEXT_DOWN:integer&field=ORD_STRA:integer&field=name:string(40)"
    )
    return add_layer(build_layer(definition, "rivers", rows))


@pytest.fixture
def regions():
    """A polygon layer covering the whole test extent."""
    rows = [
        ("POLYGON((-78 -17, -68 -17, -68 -11, -78 -11, -78 -17))", ["south"]),
    ]
    return add_layer(build_layer("Polygon?field=zone:string(20)", "regions", rows))
