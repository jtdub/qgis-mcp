"""Result shapes the QGIS MCP tools return.

FastMCP turns each TypedDict into an output schema, so an MCP client receives
structured content and does not parse a JSON string.
"""

from typing import Any

from typing_extensions import TypedDict


class PluginInfo(TypedDict):
    """What the QGIS plugin reports when the client says hello."""

    pong: bool
    protocol: int
    plugin_version: str
    qgis_version: str
    execute_code_enabled: bool


class QgisInfo(TypedDict):
    """The QGIS build the plugin runs inside."""

    qgis_version: str
    profile_folder: str
    plugins_count: int


class PixelSize(TypedDict):
    """Ground distance of one raster pixel, in the layer's own units."""

    x: float
    y: float


class FieldSummary(TypedDict):
    """A field name and its type, as listed beside a layer."""

    name: str
    type: str


class LayerInfo(TypedDict, total=False):
    """One layer of the project. The vector and raster keys are exclusive."""

    id: str
    name: str
    type: str
    visible: bool
    crs: str
    geometry_type: str
    feature_count: int
    fields: list[FieldSummary]
    band_count: int
    width: int
    height: int
    pixel_size: PixelSize


class ProjectSummary(TypedDict):
    """The project, and the first ten layers in it."""

    filename: str
    title: str
    layer_count: int
    crs: str
    layers: list[LayerInfo]


class FieldDetail(TypedDict):
    """One field of a vector layer, with its storage limits."""

    name: str
    type: str
    length: int
    precision: int
    comment: str


class FieldList(TypedDict):
    """Every field of one vector layer."""

    layer_name: str
    fields: list[FieldDetail]


class UniqueValues(TypedDict):
    """A page of the distinct values held by one field."""

    layer_name: str
    field_name: str
    total_count: int
    returned_count: int
    offset: int
    has_more: bool
    values: list[Any]


class SampledFeature(TypedDict):
    """One feature, with its geometry as truncated WGS84 WKT."""

    id: int
    attributes: dict[str, Any]
    geometry_wkt: str | None


class FeatureSample(TypedDict):
    """A page of features taken from one layer."""

    layer_name: str
    total_count: int
    returned_count: int
    offset: int
    has_more: bool
    features: list[SampledFeature]


class Extent(TypedDict):
    """A bounding box in WGS84 degrees."""

    layer_name: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float


class LayerRef(TypedDict, total=False):
    """The layer a tool just added to the project."""

    id: str
    name: str
    type: str
    feature_count: int
    width: int
    height: int


class PageDimensions(TypedDict):
    """Page width and height in millimetres."""

    width: float
    height: float


class LayoutInfo(TypedDict):
    """The print layout a tool just created."""

    name: str
    page_size: str
    orientation: str
    dimensions_mm: PageDimensions
    has_title: bool
