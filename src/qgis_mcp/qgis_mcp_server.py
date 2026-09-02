#!/usr/bin/env python3
"""QGIS MCP server.

Exposes QGIS Desktop as MCP tools. Each tool sends a command over a TCP socket
to the QGIS MCP plugin, which runs inside QGIS.
"""

import json
import logging
import os
import socket
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from functools import partial
from pathlib import Path
from typing import Any, cast

import anyio.to_thread
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from qgis_mcp.models import (
    Extent,
    FeatureSample,
    FieldList,
    LayerInfo,
    LayerRef,
    LayoutInfo,
    PluginInfo,
    ProjectSummary,
    QgisInfo,
    UniqueValues,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("QgisMCPServer")


UNAUTHENTICATED = "unauthenticated"
"""Error code the plugin returns when the token is missing or wrong."""

PROTOCOL_VERSION = 1
"""Wire protocol this server speaks. The plugin must report the same number."""

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876

_SESSION_RELATIVE_PATH = Path("qgis_mcp") / "session.json"
"""Location of the session file inside a QGIS profile directory."""


def _candidate_profile_dirs():
    """Yield the QGIS profile directories that may hold a session file."""
    home = Path.home()
    appdata = os.environ.get("APPDATA")
    if appdata:
        yield Path(appdata) / "QGIS" / "QGIS3" / "profiles" / "default"
    yield home / "Library" / "Application Support" / "QGIS" / "QGIS3" / "profiles" / "default"
    yield home / ".local" / "share" / "QGIS" / "QGIS3" / "profiles" / "default"


def _read_session_file():
    """Return the session the QGIS plugin published, or an empty dict.

    The explicit path in QGIS_MCP_SESSION_FILE wins. Otherwise the default
    profile directory for this platform is searched.
    """
    explicit = os.environ.get("QGIS_MCP_SESSION_FILE")
    paths = [Path(explicit)] if explicit else [d / _SESSION_RELATIVE_PATH for d in _candidate_profile_dirs()]
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            continue
    return {}


def resolve_session():
    """Return the host, port, and token to connect with.

    Environment variables win over the session file the plugin publishes.
    """
    session = _read_session_file()
    host = os.environ.get("QGIS_MCP_HOST") or session.get("host") or DEFAULT_HOST
    port = int(os.environ.get("QGIS_MCP_PORT") or session.get("port") or DEFAULT_PORT)
    token = os.environ.get("QGIS_MCP_TOKEN") or session.get("token") or ""
    return host, port, token


class QgisMCPServer:
    """Socket client for communicating with the QGIS MCP plugin."""

    DEFAULT_TIMEOUT = 120
    """Seconds to wait for a response. Generous, for operations such as tracing."""

    RECV_BUFFER_SIZE = 65536
    """Bytes read from the socket per recv call."""

    MAX_RESPONSE_BYTES = 50 * 1024 * 1024
    """Largest response accepted before the command is abandoned."""

    MAX_STALE_RESPONSES = 8
    """Responses with an unexpected id that are skipped before the client gives up."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, token=""):
        self.host = host
        self.port = port
        self.token = token
        self.socket: socket.socket | None = None
        self.plugin_info: dict[str, Any] = {}
        self._buffer = b""

    def connect(self):
        """Connect to the QGIS MCP server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.DEFAULT_TIMEOUT)
            self.socket.connect((self.host, self.port))
            self._buffer = b""
            logger.info(f"Connected to QGIS plugin at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to server: {str(e)}")
            self.socket = None
            return False

    def disconnect(self):
        """Disconnect from the server"""
        if self.socket:
            with suppress(Exception):
                self.socket.close()
            self.socket = None
        self._buffer = b""

    def is_open(self):
        """Return True if this client holds a socket.

        A socket that the peer already closed still counts as open. The failure
        surfaces on the next send or receive, and send_command reconnects there.
        """
        return self.socket is not None

    def _reconnect(self):
        """Attempt to reconnect to the QGIS plugin."""
        logger.info("Attempting to reconnect to QGIS plugin...")
        self.disconnect()
        return self.connect()

    def _open_socket(self):
        """Return the live socket.

        Raises:
            ConnectionError: If the socket closed between two steps of a command.
        """
        if self.socket is None:
            raise ConnectionError("The connection to QGIS closed while the command was in flight.")
        return self.socket

    def _read_line(self, command_type):
        """Return the next complete response line, without its terminator.

        Raises:
            Exception: If QGIS closes the connection or the response is too large.
        """
        while b"\n" not in self._buffer:
            chunk = self._open_socket().recv(self.RECV_BUFFER_SIZE)
            if not chunk:
                self.disconnect()
                raise Exception(f"Connection closed by QGIS while waiting for response to '{command_type}'")
            self._buffer += chunk
            if len(self._buffer) > self.MAX_RESPONSE_BYTES:
                self._buffer = b""
                raise Exception(f"Response for '{command_type}' exceeded {self.MAX_RESPONSE_BYTES} bytes")
        line, self._buffer = self._buffer.split(b"\n", 1)
        return line

    def _exchange(self, command, timeout):
        """Write one command and return the response that carries its id."""
        sock = self._open_socket()
        if timeout is not None:
            sock.settimeout(timeout)
        try:
            sock.sendall(json.dumps(command).encode("utf-8") + b"\n")
            for _ in range(self.MAX_STALE_RESPONSES + 1):
                line = self._read_line(command["type"])
                if not line.strip():
                    continue
                try:
                    response = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    raise Exception(f"QGIS sent a malformed response to '{command['type']}': {e}")
                if response.get("id") in (command["id"], None):
                    return response
                logger.warning(f"Skipping a stale response with id {response.get('id')!r}")
            raise Exception(f"QGIS never answered '{command['type']}' with a matching request id.")
        finally:
            if timeout is not None and self.socket:
                self.socket.settimeout(self.DEFAULT_TIMEOUT)

    def send_command(self, command_type, params=None, timeout=None):
        """Send a command to the server and get the response.

        The command carries a request id. A retry after a lost connection reuses
        that id, so the plugin answers from its cache instead of running a write
        for a second time.
        """
        if not self.is_open() and not self._reconnect():
            raise Exception(
                "Could not connect to QGIS. Make sure the QGIS MCP plugin is running and the server is started."
            )

        command = {
            "id": uuid.uuid4().hex,
            "protocol": PROTOCOL_VERSION,
            "type": command_type,
            "params": params or {},
            "token": self.token,
        }

        try:
            return self._exchange(command, timeout)
        except TimeoutError:
            raise Exception(
                f"Timeout waiting for response to '{command_type}'. The operation may still be running in QGIS."
            )
        except (ConnectionError, BrokenPipeError, OSError) as e:
            logger.warning(f"Connection error during '{command_type}': {e}")
            self.disconnect()
            if not self._reconnect():
                raise Exception(f"Lost connection to QGIS during '{command_type}' and could not reconnect.")
            try:
                return self._exchange(command, timeout)
            except Exception as retry_err:
                raise Exception(f"Failed to execute '{command_type}' after reconnect: {retry_err}")


_qgis_connection: QgisMCPServer | None = None

_connection_lock = threading.Lock()
"""Serializes access to the shared socket. Async tools can overlap on worker threads."""


def _handshake(connection):
    """Ask the plugin what it is, and refuse a plugin that speaks another protocol.

    Raises:
        ToolError: If the plugin reports a different protocol version.
    """
    response = connection.send_command("ping")
    if response.get("status") != "success":
        return {}
    info = response.get("result") or {}
    remote = info.get("protocol")
    if remote != PROTOCOL_VERSION:
        raise ToolError(
            f"The QGIS MCP plugin speaks protocol {remote!r} and this server speaks {PROTOCOL_VERSION}. "
            "Copy the current qgis_mcp_plugin folder into your QGIS profile, then restart QGIS."
        )
    return info


def get_qgis_connection():
    """Get or create a persistent QGIS connection."""
    global _qgis_connection

    if _qgis_connection is not None and _qgis_connection.is_open():
        return _qgis_connection

    if _qgis_connection is not None:
        logger.warning("Existing connection is no longer valid, reconnecting...")
        _qgis_connection.disconnect()
        _qgis_connection = None

    host, port, token = resolve_session()
    connection = QgisMCPServer(host=host, port=port, token=token)
    if not connection.connect():
        raise Exception(
            f"Could not connect to QGIS at {host}:{port}. Make sure the QGIS MCP plugin is running "
            "and the server is started."
        )
    if not token:
        logger.warning("No token found. Set QGIS_MCP_TOKEN to the token shown in the QGIS MCP dock.")
    try:
        connection.plugin_info = _handshake(connection)
    except Exception:
        connection.disconnect()
        raise
    _qgis_connection = connection
    return _qgis_connection


def _reset_connection():
    """Drop the cached connection so the next call re-reads the session."""
    global _qgis_connection

    if _qgis_connection is not None:
        _qgis_connection.disconnect()
        _qgis_connection = None


def _send(command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a command to QGIS and return its result payload.

    Parameters whose value is None are omitted, so a caller can pass an optional
    argument through unconditionally.

    Raises:
        ToolError: If QGIS reports an error for the command.
    """
    supplied = {key: value for key, value in (params or {}).items() if value is not None}
    with _connection_lock:
        response = get_qgis_connection().send_command(command, supplied)
        if response.get("code") == UNAUTHENTICATED:
            logger.warning("The token was rejected. Reading the session again and retrying once.")
            _reset_connection()
            response = get_qgis_connection().send_command(command, supplied)
    if response.get("status") == "error":
        raise ToolError(response.get("message") or f"QGIS reported an error for '{command}'")
    return response.get("result")


async def _run(command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a command to QGIS from a worker thread.

    The socket read blocks for up to two minutes, so it must not run on the
    event loop. Every tool goes through this helper.
    """
    return await anyio.to_thread.run_sync(partial(_send, command, params))


async def _run_json(command: str, params: dict[str, Any] | None = None) -> str:
    """Send a command to QGIS and return its result as compact JSON."""
    return json.dumps(await _run(command, params), separators=(",", ":"))


async def _run_watched(ctx: Context, note: str, command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a slow command, and tell the client that it started and finished.

    QGIS answers only once, so the progress goes from nothing to complete. The
    client still sees that the call is alive.
    """
    await ctx.info(note)
    await ctx.report_progress(0, 1)
    result = await _run(command, params)
    await ctx.report_progress(1, 1)
    return result


async def _plugin_info() -> dict[str, Any]:
    """Return what the plugin reports about itself, read fresh.

    The user can change the execute_code setting at any time, so the cached
    handshake is not trusted for that flag.
    """
    info: dict[str, Any] = await _run("ping")
    with _connection_lock:
        if _qgis_connection is not None:
            _qgis_connection.plugin_info = info
    return info


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage server startup and shutdown lifecycle.

    The startup probe runs on a worker thread. The socket connect and the
    handshake must never block the event loop.
    """
    try:
        logger.info("QgisMCPServer server starting up")

        try:
            await anyio.to_thread.run_sync(get_qgis_connection)
            logger.info("Successfully connected to Qgis on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Qgis on startup: {str(e)}")
            logger.warning("Make sure the Qgis addon is running before using Qgis resources or tools")

        # Return an empty context - we're using the global connection
        yield {}
    finally:
        # Clean up the global connection on shutdown
        global _qgis_connection
        if _qgis_connection:
            logger.info("Disconnecting from Qgis on shutdown")
            _qgis_connection.disconnect()
            _qgis_connection = None
        logger.info("QgisMCPServer server shut down")


def _annotate(title, *, read_only=False, destructive=False, idempotent=False, open_world=False):
    """Describe how a tool affects the QGIS session, for the MCP client."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
    )


mcp = FastMCP(
    "qgis",
    instructions=(
        "Drives a running QGIS Desktop session through the QGIS MCP plugin.\n"
        "Call list_layers first, to learn the layer names, the CRSs, and the field names.\n"
        "Call get_layer_fields and get_unique_values before you write an expression.\n"
        "All coordinates in and out are WGS84 (EPSG:4326). The plugin reprojects internally.\n"
        "Every tool takes a layer name. A layer id from list_layers also works.\n"
        "A result that carries has_more is one page. Ask for the next page with offset.\n"
        "Prefer a specific tool over execute_code. The user must enable execute_code in the QGIS dock.\n"
        "For a map, call create_print_layout, then add_legend or add_inset_map, then export_layout."
    ),
    lifespan=server_lifespan,
)


@mcp.tool(annotations=_annotate("Ping QGIS", read_only=True, idempotent=True))
async def ping(ctx: Context) -> PluginInfo:
    """Check that QGIS answers, and report the plugin and protocol versions."""
    return cast(PluginInfo, await _run("ping"))


@mcp.tool(annotations=_annotate("Get QGIS Info", read_only=True, idempotent=True))
async def get_qgis_info(ctx: Context) -> QgisInfo:
    """Get QGIS information"""
    return cast(QgisInfo, await _run("get_qgis_info"))


@mcp.tool(annotations=_annotate("Load Project", destructive=True, idempotent=True, open_world=True))
async def load_project(ctx: Context, path: str) -> str:
    """Load a QGIS project from the specified path."""
    return await _run_json("load_project", {"path": path})


@mcp.tool(annotations=_annotate("Create New Project", destructive=True, idempotent=True, open_world=True))
async def create_new_project(ctx: Context, path: str) -> str:
    """Create a new project and save it."""
    return await _run_json("create_new_project", {"path": path})


@mcp.tool(annotations=_annotate("Get Project Info", read_only=True, idempotent=True))
async def get_project_info(ctx: Context) -> ProjectSummary:
    """Get current project information"""
    return cast(ProjectSummary, await _run("get_project_info"))


@mcp.tool(annotations=_annotate("Add Vector Layer", open_world=True))
async def add_vector_layer(ctx: Context, path: str, provider: str = "ogr", name: str | None = None) -> LayerRef:
    """Add a vector layer to the project."""
    return cast(LayerRef, await _run("add_vector_layer", {"path": path, "provider": provider, "name": name}))


@mcp.tool(annotations=_annotate("Add Raster Layer", open_world=True))
async def add_raster_layer(ctx: Context, path: str, provider: str = "gdal", name: str | None = None) -> LayerRef:
    """Add a raster layer to the project."""
    return cast(LayerRef, await _run("add_raster_layer", {"path": path, "provider": provider, "name": name}))


@mcp.tool(annotations=_annotate("List Layers", read_only=True, idempotent=True))
async def list_layers(ctx: Context) -> list[LayerInfo]:
    """List all layers with rich metadata including CRS, fields, geometry type, and feature count.

    Returns an array of layer objects. Vector layers include field definitions.
    Raster layers include band count, dimensions, and pixel size.
    """
    return cast(list[LayerInfo], await _run("list_layers"))


@mcp.tool(annotations=_annotate("Remove Layer", destructive=True))
async def remove_layer(ctx: Context, layer: str) -> str:
    """Remove a layer from the project by its name or its id."""
    return await _run_json("remove_layer", {"layer": layer})


@mcp.tool(annotations=_annotate("Zoom To Layer", idempotent=True))
async def zoom_to_layer(ctx: Context, layer: str) -> str:
    """Zoom to the extent of a layer, named by its name or its id."""
    return await _run_json("zoom_to_layer", {"layer": layer})


@mcp.tool(annotations=_annotate("Get Layer Features", read_only=True, idempotent=True))
async def get_layer_features(ctx: Context, layer: str, limit: int = 10, offset: int = 0) -> FeatureSample:
    """Read one page of features from a vector layer.

    The layer is named by its name or its id. Read the next page with offset.
    """
    return cast(FeatureSample, await _run("get_layer_features", {"layer": layer, "limit": limit, "offset": offset}))


@mcp.tool(annotations=_annotate("Execute Processing", destructive=True, open_world=True))
async def execute_processing(ctx: Context, algorithm: str, parameters: dict) -> str:
    """Execute a processing algorithm with the given parameters."""
    return await _run_json("execute_processing", {"algorithm": algorithm, "parameters": parameters})


@mcp.tool(annotations=_annotate("Save Project", destructive=True, idempotent=True, open_world=True))
async def save_project(ctx: Context, path: str | None = None) -> str:
    """Save the current project to the given path, or to the current project path if not specified."""
    return await _run_json("save_project", {"path": path})


@mcp.tool(annotations=_annotate("Render Map", destructive=True, idempotent=True, open_world=True))
async def render_map(ctx: Context, path: str, width: int = 800, height: int = 600) -> str:
    """Render the current map view to an image file with the specified dimensions."""
    result = await _run_watched(
        ctx,
        f"Rendering the canvas to {path} at {width}x{height}.",
        "render_map",
        {"path": path, "width": width, "height": height},
    )
    return json.dumps(result, separators=(",", ":"))


@mcp.tool(annotations=_annotate("Execute PyQGIS Code", destructive=True, open_world=True))
async def execute_code(ctx: Context, code: str) -> str:
    """Execute arbitrary PyQGIS code provided as a string.

    WARNING: This runs unrestricted Python inside the QGIS process. Prefer a
    specific tool when one exists.

    Returns:
        The captured stdout and stderr of the code.

    Raises:
        ToolError: If the code raises, or if the QGIS dock does not allow it.
    """
    if (await _plugin_info()).get("execute_code_enabled") is False:
        raise ToolError(
            "execute_code is disabled. Tick 'Allow execute_code' in the QGIS MCP dock, then call this tool again."
        )
    result = await _run("execute_code", {"code": code})
    if isinstance(result, dict) and result.get("executed") is False:
        raise ToolError(result.get("traceback") or result.get("error") or "The PyQGIS code failed.")
    return json.dumps(result, separators=(",", ":"))


# Phase 1: Introspection Tools


@mcp.tool(annotations=_annotate("Get Layer Fields", read_only=True, idempotent=True))
async def get_layer_fields(ctx: Context, layer_name: str) -> FieldList:
    """Get detailed field information for a vector layer.

    Returns field name, type, length, precision, and comment for each field.
    """
    return cast(FieldList, await _run("get_layer_fields", {"layer_name": layer_name}))


@mcp.tool(annotations=_annotate("Get Unique Values", read_only=True, idempotent=True))
async def get_unique_values(
    ctx: Context, layer_name: str, field_name: str, limit: int = 50, offset: int = 0
) -> UniqueValues:
    """Read one page of the distinct values a field holds.

    The values are sorted. total_count is the size of the whole set, and
    has_more says whether another page follows. Read that page with offset.
    """
    return cast(
        UniqueValues,
        await _run(
            "get_unique_values",
            {
                "layer_name": layer_name,
                "field_name": field_name,
                "limit": limit,
                "offset": offset,
            },
        ),
    )


@mcp.tool(annotations=_annotate("Sample Features", read_only=True, idempotent=True))
async def sample_features(
    ctx: Context, layer_name: str, count: int = 5, expression: str | None = None, offset: int = 0
) -> FeatureSample:
    """Sample features from a vector layer with optional expression filter.

    Returns feature attributes and truncated WKT geometry in WGS84.
    Use expression parameter to filter (e.g., \"name\" = 'Vilcanota').
    """
    return cast(
        FeatureSample,
        await _run(
            "sample_features",
            {"layer_name": layer_name, "count": count, "expression": expression, "offset": offset},
        ),
    )


@mcp.tool(annotations=_annotate("Get Layer Extent", read_only=True, idempotent=True))
async def get_layer_extent(ctx: Context, layer_name: str) -> Extent:
    """Get a layer's bounding box in WGS84 coordinates.

    Returns xmin, ymin, xmax, ymax of the layer extent.
    """
    return cast(Extent, await _run("get_layer_extent", {"layer_name": layer_name}))


# Phase 2: Filtering & Spatial Operations


@mcp.tool(annotations=_annotate("Filter Layer"))
async def filter_layer(ctx: Context, layer_name: str, expression: str, output_name: str) -> str:
    """Create a new memory layer from features matching a QGIS expression.

    Examples: "name" IN ('Vilcanota', 'Urubamba'), "population" > 10000
    The output layer is created in WGS84 and added to the project.
    """
    result = await _run_watched(
        ctx,
        f"Filtering '{layer_name}' into '{output_name}'.",
        "filter_layer",
        {
            "layer_name": layer_name,
            "expression": expression,
            "output_name": output_name,
        },
    )
    return json.dumps(result, separators=(",", ":"))


@mcp.tool(annotations=_annotate("Trace Downstream"))
async def trace_downstream(
    ctx: Context,
    layer_name: str,
    start_lon: float,
    start_lat: float,
    id_field: str = "HYRIV_ID",
    next_down_field: str = "NEXT_DOWN",
    output_name: str = "traced_river",
) -> str:
    """Trace a river network downstream from a WGS84 coordinate.

    Follows the network topology using id_field and next_down_field pointers.
    Compatible with HydroSHEDS/HydroRIVERS data. Creates an output memory layer.
    """
    result = await _run_watched(
        ctx,
        f"Tracing '{layer_name}' downstream from {start_lon}, {start_lat}.",
        "trace_downstream",
        {
            "layer_name": layer_name,
            "start_lon": start_lon,
            "start_lat": start_lat,
            "id_field": id_field,
            "next_down_field": next_down_field,
            "output_name": output_name,
        },
    )
    return json.dumps(result, separators=(",", ":"))


@mcp.tool(annotations=_annotate("Set Layer Visibility", idempotent=True))
async def set_layer_visibility(ctx: Context, layer_name: str, visible: bool) -> str:
    """Toggle layer visibility in the layer tree."""
    return await _run_json(
        "set_layer_visibility",
        {
            "layer_name": layer_name,
            "visible": visible,
        },
    )


@mcp.tool(annotations=_annotate("Set Canvas Extent", idempotent=True))
async def set_canvas_extent(ctx: Context, xmin: float, ymin: float, xmax: float, ymax: float) -> str:
    """Set the map canvas extent using WGS84 coordinates.

    Automatically reprojects to the project CRS.
    """
    return await _run_json(
        "set_canvas_extent",
        {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
        },
    )


# Phase 3: Styling Tools


@mcp.tool(annotations=_annotate("Style Line Graduated", idempotent=True))
async def style_line_graduated(
    ctx: Context,
    layer_name: str,
    width_field: str,
    color: str = "#1a5276",
    min_width: float = 0.3,
    max_width: float = 3.5,
    num_classes: int = 0,
) -> str:
    """Apply graduated line width styling based on a numeric field.

    Creates classes with interpolated widths. Set num_classes=0 for auto-detection.
    """
    return await _run_json(
        "style_line_graduated",
        {
            "layer_name": layer_name,
            "width_field": width_field,
            "color": color,
            "min_width": min_width,
            "max_width": max_width,
            "num_classes": num_classes,
        },
    )


@mcp.tool(annotations=_annotate("Style Simple", idempotent=True))
async def style_simple(
    ctx: Context,
    layer_name: str,
    color: str = "#333333",
    outline_color: str = "#000000",
    width: float = 0.5,
    opacity: float = 1.0,
) -> str:
    """Apply simple single-symbol styling to a vector layer.

    Automatically detects geometry type (point/line/polygon) and creates
    the appropriate symbol.
    """
    return await _run_json(
        "style_simple",
        {
            "layer_name": layer_name,
            "color": color,
            "outline_color": outline_color,
            "width": width,
            "opacity": opacity,
        },
    )


@mcp.tool(annotations=_annotate("Style Categorized", idempotent=True))
async def style_categorized(
    ctx: Context, layer_name: str, field_name: str, color_ramp: str = "Spectral", width: float = 1.0
) -> str:
    """Apply categorized styling using unique field values and a color ramp.

    Each unique value gets a distinct color from the ramp.
    """
    return await _run_json(
        "style_categorized",
        {
            "layer_name": layer_name,
            "field_name": field_name,
            "color_ramp": color_ramp,
            "width": width,
        },
    )


@mcp.tool(annotations=_annotate("Add Labels", idempotent=True))
async def add_labels(
    ctx: Context,
    layer_name: str,
    field_name: str,
    font_size: float = 10,
    color: str = "#1a1a1a",
    follow_line: bool = True,
    buffer_size: float = 1.0,
    font_family: str = "Noto Sans",
) -> str:
    """Add labels to a vector layer.

    Supports curved labels that follow line geometry. Includes a white
    buffer/halo for readability.
    """
    return await _run_json(
        "add_labels",
        {
            "layer_name": layer_name,
            "field_name": field_name,
            "font_size": font_size,
            "color": color,
            "follow_line": follow_line,
            "buffer_size": buffer_size,
            "font_family": font_family,
        },
    )


# Phase 4: Print Layout & Cartography


@mcp.tool(annotations=_annotate("Create Print Layout"))
async def create_print_layout(
    ctx: Context,
    name: str,
    page_size: str = "A3",
    orientation: str = "landscape",
    title: str | None = None,
    replace: bool = False,
) -> LayoutInfo:
    """Create a print layout with a map item, scale bar, and north arrow.

    Supports page sizes: A3, A4, letter, tabloid.
    The main map item is set to the current canvas extent.
    Set replace to true to overwrite a layout that already has this name.
    """
    return cast(
        LayoutInfo,
        await _run(
            "create_print_layout",
            {"name": name, "page_size": page_size, "orientation": orientation, "title": title, "replace": replace},
        ),
    )


@mcp.tool(annotations=_annotate("Add Legend"))
async def add_legend(
    ctx: Context,
    layout_name: str,
    title: str = "Legend",
    position: list[Any] | None = None,
    width: float = 45,
    layers: list[Any] | None = None,
    background: bool = True,
) -> str:
    """Add a legend to a print layout.

    Optionally filter to specific layer names. Position is [x, y] in mm.
    """
    return await _run_json(
        "add_legend",
        {
            "layout_name": layout_name,
            "title": title,
            "width": width,
            "background": background,
            "position": position,
            "layers": layers,
        },
    )


@mcp.tool(annotations=_annotate("Add Inset Map"))
async def add_inset_map(
    ctx: Context,
    layout_name: str,
    extent: list[Any],
    position: list[Any] | None = None,
    size: list[Any] | None = None,
    layers: list[Any] | None = None,
    show_extent_indicator: bool = True,
) -> str:
    """Add an inset/overview map to a print layout.

    extent is [xmin, ymin, xmax, ymax] in WGS84.
    Shows a red rectangle indicating the main map's extent.
    """
    return await _run_json(
        "add_inset_map",
        {
            "layout_name": layout_name,
            "extent": extent,
            "show_extent_indicator": show_extent_indicator,
            "position": position,
            "size": size,
            "layers": layers,
        },
    )


@mcp.tool(annotations=_annotate("Export Layout", destructive=True, idempotent=True, open_world=True))
async def export_layout(ctx: Context, layout_name: str, output_path: str, dpi: int = 300) -> str:
    """Export a print layout to PDF or image.

    File extension determines format: .pdf for PDF, .png/.jpg for images.
    """
    result = await _run_watched(
        ctx,
        f"Exporting the layout '{layout_name}' to {output_path} at {dpi} dpi.",
        "export_layout",
        {
            "layout_name": layout_name,
            "output_path": output_path,
            "dpi": dpi,
        },
    )
    return json.dumps(result, separators=(",", ":"))


def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
