import contextlib
import hmac
import io
import json
import os
import secrets
import socket
import time
import traceback
from collections import OrderedDict

from qgis.core import (
    NULL,
    Qgis,
    QgsApplication,  # Rendering; Print Layout; Labels
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsExpression,
    QgsFeature,
    QgsFeatureRequest,
    QgsFillSymbol,
    QgsGeometry,
    QgsGraduatedSymbolRenderer,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemMapOverview,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMapLayer,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsMarkerSymbol,
    QgsMessageLog,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsRendererCategory,
    QgsRendererRange,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QObject, QRectF, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QDockWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qgis.utils import active_plugins

PROTOCOL_VERSION = 1
"""Wire protocol this plugin speaks. The MCP server must send the same number."""

PLUGIN_VERSION = "0.2.0"
"""Version of this plugin, reported to the client by ping."""


class QgisMCPServer(QObject):
    """Server class to handle socket connections and execute QGIS commands"""

    MAX_REQUEST_BYTES = 8 * 1024 * 1024
    """Largest request the server will buffer before it drops the client."""

    MAX_FEATURES_PER_REQUEST = 1000
    """Upper bound on the features any single handler returns."""

    MAX_WKT_CHARS = 200
    """Longest WKT string returned for one feature."""

    RECV_CHUNK_BYTES = 8192
    """Bytes read from the client per poll."""

    SEND_TIMEOUT = 30
    """Seconds allowed to write one response before the client is dropped."""

    POLL_INTERVAL_MS = 20
    """Milliseconds between polls of the listening socket."""

    RESPONSE_CACHE_SIZE = 16
    """Answered requests kept, so a retry with the same id does not run twice."""

    FEATURE_BATCH_SIZE = 1000
    """Features written to a memory layer in one call, and the UI repaint interval."""

    MAX_TRACE_SEGMENTS = 50000
    """Segments a downstream trace follows before it gives up on the topology."""

    DEFAULT_GRADUATED_CLASSES = 5
    """Equal-interval classes a graduated renderer gets when the caller names none."""

    PUMP_INTERVAL_SECONDS = 0.05
    """Shortest gap between two repaints of the QGIS window during a handler."""

    WKT_PRECISION = 6
    """Decimal places kept in the WGS84 WKT a feature page returns."""

    def __init__(self, host="127.0.0.1", port=9876, iface=None, token=None, allow_execute_code=False):
        super().__init__()
        self.host = host
        self.port = port
        self.iface = iface
        self.token = token or secrets.token_urlsafe(32)
        self.allow_execute_code = allow_execute_code
        self.running = False
        self.socket = None
        self.client = None
        self.buffer = b""
        self.timer = None
        self.answered = OrderedDict()
        self._last_pump = 0.0

    def session_file_path(self):
        """Return the path of the file that publishes this server's token."""
        return os.path.join(QgsApplication.qgisSettingsDirPath(), "qgis_mcp", "session.json")

    def _write_session_file(self):
        """Publish the host, port, and token so a local client can find them."""
        path = self.session_file_path()
        directory = os.path.dirname(path)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        payload = {"host": self.host, "port": self.port, "token": self.token, "pid": os.getpid()}
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def _remove_session_file(self):
        """Delete the published session file."""
        with contextlib.suppress(OSError):
            os.remove(self.session_file_path())

    def start(self):
        """Start the server"""
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            self.socket.setblocking(False)

            self.timer = QTimer()
            self.timer.timeout.connect(self.process_server)
            self.timer.start(self.POLL_INTERVAL_MS)

            try:
                self._write_session_file()
            except OSError as e:
                QgsMessageLog.logMessage(
                    f"Could not write the session file, so the client needs QGIS_MCP_TOKEN: {str(e)}",
                    "QGIS MCP",
                    Qgis.Warning,
                )

            QgsMessageLog.logMessage(f"QGIS MCP server started on {self.host}:{self.port}", "QGIS MCP")
            return True
        except Exception as e:
            QgsMessageLog.logMessage(f"Failed to start server: {str(e)}", "QGIS MCP", Qgis.Critical)
            self.stop()
            return False

    def stop(self):
        """Stop the server"""
        self.running = False

        if self.timer:
            self.timer.stop()
            self.timer = None

        if self.socket:
            with contextlib.suppress(Exception):
                self.socket.close()
        if self.client:
            with contextlib.suppress(Exception):
                self.client.close()

        self.socket = None
        self.client = None
        self.buffer = b""
        self._remove_session_file()
        QgsMessageLog.logMessage("QGIS MCP server stopped", "QGIS MCP")

    def process_server(self):
        """Process server operations (called by timer)"""
        if not self.running:
            return

        try:
            # Accept new connections
            if not self.client and self.socket:
                try:
                    self.client, address = self.socket.accept()
                    self.client.setblocking(False)
                    QgsMessageLog.logMessage(f"Connected to client: {address}", "QGIS MCP")
                except BlockingIOError:
                    pass  # No connection waiting
                except Exception as e:
                    QgsMessageLog.logMessage(f"Error accepting connection: {str(e)}", "QGIS MCP", Qgis.Warning)

            if self.client:
                self._process_client()

        except Exception as e:
            QgsMessageLog.logMessage(f"Server error: {str(e)}", "QGIS MCP", Qgis.Critical)

    def _drop_client(self, reason, level=None):
        """Close the current client connection and clear its buffer."""
        QgsMessageLog.logMessage(reason, "QGIS MCP", level if level is not None else Qgis.Info)
        if self.client:
            with contextlib.suppress(Exception):
                self.client.close()
        self.client = None
        self.buffer = b""

    def _send_response(self, payload):
        """Write one newline-terminated response to the client.

        A payload that cannot be serialized is replaced by an error response, so
        the client always receives an answer instead of a dropped connection.
        """
        if not self.client:
            return
        try:
            body = json.dumps(payload).encode("utf-8")
        except (TypeError, ValueError) as e:
            QgsMessageLog.logMessage(f"Response is not JSON serializable: {str(e)}", "QGIS MCP", Qgis.Critical)
            request_id = payload.get("id") if isinstance(payload, dict) else None
            body = json.dumps(self._error(request_id, f"Result is not JSON serializable: {str(e)}")).encode("utf-8")
        self.client.settimeout(self.SEND_TIMEOUT)
        try:
            self.client.sendall(body + b"\n")
        finally:
            if self.client:
                self.client.setblocking(False)

    def _remember(self, request_id, response):
        """Cache one answered request, so a retry with the same id is free."""
        self.answered[request_id] = response
        while len(self.answered) > self.RESPONSE_CACHE_SIZE:
            self.answered.popitem(last=False)

    def _answer(self, command):
        """Return the response for one command, from the cache when possible."""
        request_id = command.get("id") if isinstance(command, dict) else None
        if isinstance(request_id, str) and request_id in self.answered:
            QgsMessageLog.logMessage(f"Answering repeated request {request_id} from the cache", "QGIS MCP")
            return self.answered[request_id]
        response = self.execute_command(command)
        if isinstance(request_id, str):
            self._remember(request_id, response)
        return response

    def _process_client(self):
        """Read one chunk from the client, and answer every complete request in it."""
        try:
            data = self.client.recv(self.RECV_CHUNK_BYTES)
        except BlockingIOError:
            return
        except Exception as e:
            self._drop_client(f"Error receiving data: {str(e)}", Qgis.Warning)
            return

        if not data:
            self._drop_client("Client disconnected")
            return

        self.buffer += data
        if len(self.buffer) > self.MAX_REQUEST_BYTES:
            self.buffer = b""
            with contextlib.suppress(Exception):
                self._send_response(self._error(None, f"Request exceeded {self.MAX_REQUEST_BYTES} bytes."))
            self._drop_client("Request too large", Qgis.Warning)
            return

        while self.client and b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                command = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                response = self._error(None, f"The request is not valid JSON: {str(e)}")
            else:
                response = self._answer(command)
            try:
                self._send_response(response)
            except Exception as e:
                self._drop_client(f"Error sending response: {str(e)}", Qgis.Warning)
                return

    def _token_is_valid(self, supplied):
        """Return True if the supplied token matches this server's token."""
        if not isinstance(supplied, str):
            return False
        return hmac.compare_digest(supplied, self.token)

    def _stamp(self, request_id, payload):
        """Add the request id and the protocol version to a response."""
        payload["id"] = request_id
        payload["protocol"] = PROTOCOL_VERSION
        return payload

    def _envelope(self, command, payload):
        """Stamp a response with the id the command carried."""
        return self._stamp(command.get("id") if isinstance(command, dict) else None, payload)

    def _error(self, request_id, message, code=None):
        """Return a stamped error response."""
        payload = {"status": "error", "message": message}
        if code is not None:
            payload["code"] = code
        return self._stamp(request_id, payload)

    def execute_command(self, command):
        """Execute a command"""
        try:
            cmd_type = command.get("type")
            params = command.get("params", {})

            if not self._token_is_valid(command.get("token")):
                QgsMessageLog.logMessage(
                    f"Rejected '{cmd_type}': the token is missing or wrong.", "QGIS MCP", Qgis.Warning
                )
                return self._error(
                    command.get("id"),
                    "Authentication failed. Set QGIS_MCP_TOKEN to the token shown in the QGIS MCP dock, "
                    "or let the client read it from the session file.",
                    code="unauthenticated",
                )

            if command.get("protocol") != PROTOCOL_VERSION:
                return self._error(
                    command.get("id"),
                    f"This plugin speaks protocol {PROTOCOL_VERSION} and the client sent "
                    f"{command.get('protocol')!r}. Update the qgis_mcp package and the plugin together.",
                    code="protocol_mismatch",
                )

            handlers = {
                "ping": self.ping,
                "get_qgis_info": self.get_qgis_info,
                "load_project": self.load_project,
                "get_project_info": self.get_project_info,
                "execute_code": self.execute_code,
                "add_vector_layer": self.add_vector_layer,
                "add_raster_layer": self.add_raster_layer,
                "list_layers": self.list_layers,
                "remove_layer": self.remove_layer,
                "zoom_to_layer": self.zoom_to_layer,
                "get_layer_features": self.get_layer_features,
                "execute_processing": self.execute_processing,
                "save_project": self.save_project,
                "render_map": self.render_map,
                "create_new_project": self.create_new_project,
                "get_layer_fields": self.get_layer_fields,
                "get_unique_values": self.get_unique_values,
                "sample_features": self.sample_features,
                "get_layer_extent": self.get_layer_extent,
                "filter_layer": self.filter_layer,
                "trace_downstream": self.trace_downstream,
                "set_layer_visibility": self.set_layer_visibility,
                "set_canvas_extent": self.set_canvas_extent,
                "style_line_graduated": self.style_line_graduated,
                "style_simple": self.style_simple,
                "style_categorized": self.style_categorized,
                "add_labels": self.add_labels,
                "create_print_layout": self.create_print_layout,
                "add_legend": self.add_legend,
                "add_inset_map": self.add_inset_map,
                "export_layout": self.export_layout,
            }

            handler = handlers.get(cmd_type)
            if handler:
                try:
                    QgsMessageLog.logMessage(f"Executing handler for {cmd_type}", "QGIS MCP")
                    result = handler(**params)
                    QgsMessageLog.logMessage("Handler execution complete", "QGIS MCP")
                    return self._envelope(command, {"status": "success", "result": result})
                except Exception as e:
                    QgsMessageLog.logMessage(f"Error in handler: {str(e)}", "QGIS MCP", Qgis.Critical)
                    traceback.print_exc()
                    return self._error(command.get("id"), str(e))
            return self._error(command.get("id"), f"Unknown command type: {cmd_type}")

        except Exception as e:
            QgsMessageLog.logMessage(f"Error executing command: {str(e)}", "QGIS MCP", Qgis.Critical)
            traceback.print_exc()
            return self._error(command.get("id"), str(e))

    def _pump_ui(self):
        """Let QGIS repaint during a long handler.

        A handler may call this on every iteration. The throttle keeps the cost
        bounded, so no handler has to pick a rate of its own.
        """
        now = time.monotonic()
        if now - self._last_pump < self.PUMP_INTERVAL_SECONDS:
            return
        self._last_pump = now
        with contextlib.suppress(Exception):
            QApplication.processEvents()

    def _resolve_layer(self, layer):
        """Find a layer by its id or by its name.

        Raises:
            Exception: If no layer matches. The message names every id and name.
        """
        project = QgsProject.instance()
        found = project.mapLayer(layer)
        if found is not None:
            return found
        for candidate in project.mapLayers().values():
            if candidate.name() == layer:
                return candidate
        raise Exception(
            f"Layer '{layer}' not found. Available layers: {[lyr.name() for lyr in project.mapLayers().values()]}. "
            f"Available ids: {list(project.mapLayers().keys())}"
        )

    def _require_vector(self, layer, label):
        """Raise unless the layer holds vector features."""
        if layer.type() != QgsMapLayer.VectorLayer:
            raise Exception(f"Layer '{label}' is not a vector layer")
        return layer

    def _wgs84_crs(self):
        """Return the WGS84 CRS."""
        return QgsCoordinateReferenceSystem("EPSG:4326")

    def _transform(self, source_crs, target_crs):
        """Return a reusable transform, or None when the two CRSs match.

        Build this once and use it for every feature. A transform built inside
        a loop costs a CRS lookup and a PROJ context for each feature.
        """
        if source_crs == target_crs:
            return None
        return QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())

    def _transform_rect(self, rect, source_crs, target_crs):
        """Return a bounding box reprojected between two CRSs.

        Raises:
            Exception: If the reprojection fails.
        """
        xform = self._transform(source_crs, target_crs)
        if xform is None:
            return rect
        try:
            return xform.transformBoundingBox(rect)
        except QgsCsException as exc:
            raise Exception(f"Cannot reproject from {source_crs.authid()} to {target_crs.authid()}: {exc}") from exc

    def _rect_to_wgs84(self, rect, source_crs):
        """Return a bounding box in WGS84."""
        return self._transform_rect(rect, source_crs, self._wgs84_crs())

    def _rect_from_wgs84(self, rect, target_crs):
        """Return a WGS84 bounding box in the target CRS."""
        return self._transform_rect(rect, self._wgs84_crs(), target_crs)

    def _point_from_wgs84(self, point, target_crs):
        """Return a WGS84 point in the target CRS.

        Raises:
            Exception: If the reprojection fails.
        """
        xform = self._transform(self._wgs84_crs(), target_crs)
        if xform is None:
            return point
        try:
            return xform.transform(point)
        except QgsCsException as exc:
            raise Exception(f"Cannot reproject to {target_crs.authid()}: {exc}") from exc

    def _apply_transform(self, geom, xform, source_crs, target_crs):
        """Return a copy of geom moved by a transform built once for many features.

        Raises:
            Exception: If the reprojection fails.
        """
        if xform is None:
            return QgsGeometry(geom)
        reprojected = QgsGeometry(geom)
        try:
            outcome = reprojected.transform(xform)
        except QgsCsException as exc:
            raise Exception(f"Cannot reproject from {source_crs.authid()} to {target_crs.authid()}: {exc}") from exc
        if outcome != QgsGeometry.Success:
            raise Exception(
                f"Reprojection from {source_crs.authid()} to {target_crs.authid()} failed (code {outcome})."
            )
        return reprojected

    def _reproject(self, geom, source_crs, target_crs):
        """Return a copy of geom reprojected between two CRSs."""
        return self._apply_transform(geom, self._transform(source_crs, target_crs), source_crs, target_crs)

    def _transform_to_wgs84(self, geom, source_crs):
        """Transform a geometry to WGS84. Returns a new geometry."""
        return self._reproject(geom, source_crs, self._wgs84_crs())

    def _transform_from_wgs84(self, geom, target_crs):
        """Transform a geometry from WGS84 to target CRS."""
        return self._reproject(geom, self._wgs84_crs(), target_crs)

    def _geometry_type_name(self, layer):
        """Get human-readable geometry type name for a vector layer.

        Raises:
            Exception: If the layer has no usable geometry type.
        """
        geom_type = layer.geometryType()
        wkb_type = layer.wkbType()
        type_map = {
            QgsWkbTypes.PointGeometry: "Point",
            QgsWkbTypes.LineGeometry: "LineString",
            QgsWkbTypes.PolygonGeometry: "Polygon",
        }
        base = type_map.get(geom_type)
        if base is None:
            raise Exception(
                f"Layer '{layer.name()}' has no point, line, or polygon geometry, "
                f"so it cannot be copied to a memory layer."
            )
        if QgsWkbTypes.isMultiType(wkb_type):
            base = "Multi" + base
        return base

    def _symbol_for(self, layer, color, outline_color="#000000", width=0.5):
        """Return a symbol that suits the layer's geometry.

        Raises:
            Exception: If the layer has no point, line, or polygon geometry.
        """
        geom_type = layer.geometryType()
        if geom_type == QgsWkbTypes.LineGeometry:
            return QgsLineSymbol.createSimple(
                {"color": color, "width": str(width), "capstyle": "round", "joinstyle": "round"}
            )
        if geom_type == QgsWkbTypes.PolygonGeometry:
            return QgsFillSymbol.createSimple(
                {"color": color, "outline_color": outline_color, "outline_width": str(width)}
            )
        if geom_type == QgsWkbTypes.PointGeometry:
            return QgsMarkerSymbol.createSimple(
                {"color": color, "outline_color": outline_color, "outline_width": str(width), "size": "3"}
            )
        raise Exception(f"Layer '{layer.name()}' has a geometry type that cannot be styled.")

    def _truncate_wkt(self, wkt):
        """Shorten a WKT string so one feature cannot fill the response."""
        if len(wkt) <= self.MAX_WKT_CHARS:
            return wkt
        return wkt[: self.MAX_WKT_CHARS] + "..."

    def _create_wgs84_memory_layer(self, source_layer, output_name):
        """Create an empty WGS84 memory layer with the source layer's fields.

        Raises:
            Exception: If the layer cannot be created.
        """
        geom_type = self._geometry_type_name(source_layer)
        mem_layer = QgsVectorLayer(f"{geom_type}?crs=EPSG:4326", output_name, "memory")
        if not mem_layer.isValid():
            raise Exception(f"Could not create the memory layer '{output_name}' for geometry type '{geom_type}'.")
        mem_layer.dataProvider().addAttributes(source_layer.fields().toList())
        mem_layer.updateFields()
        return mem_layer

    def ping(self, **kwargs):
        """Report that the plugin is alive, and what it supports."""
        return {
            "pong": True,
            "protocol": PROTOCOL_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "qgis_version": Qgis.version(),
            "execute_code_enabled": bool(self.allow_execute_code),
        }

    def get_qgis_info(self, **kwargs):
        """Get basic QGIS information"""
        return {
            "qgis_version": Qgis.version(),
            "profile_folder": QgsApplication.qgisSettingsDirPath(),
            "plugins_count": len(active_plugins),
        }

    def get_project_info(self, **kwargs):
        """Get information about the current QGIS project"""
        project = QgsProject.instance()

        # Get basic project information
        info = {
            "filename": project.fileName(),
            "title": project.title(),
            "layer_count": len(project.mapLayers()),
            "crs": project.crs().authid(),
            "layers": [],
        }

        # Add basic layer information (limit to 10 layers for performance)
        layers = list(project.mapLayers().values())
        for i, layer in enumerate(layers):
            if i >= 10:  # Limit to 10 layers
                break

            layer_info = {
                "id": layer.id(),
                "name": layer.name(),
                "type": self._get_layer_type(layer),
                "visible": layer.isValid() and project.layerTreeRoot().findLayer(layer.id()).isVisible(),
            }
            info["layers"].append(layer_info)

        return info

    def _get_layer_type(self, layer):
        """Helper to get layer type as string"""
        if layer.type() == QgsMapLayer.VectorLayer:
            return f"vector_{layer.geometryType()}"
        elif layer.type() == QgsMapLayer.RasterLayer:
            return "raster"
        else:
            return str(layer.type())

    def execute_code(self, code, **kwargs):
        """Execute arbitrary PyQGIS code.

        The redirect is undone even when the code raises BaseException, so the
        QGIS console keeps its own stdout.

        Raises:
            Exception: If the dock widget does not allow code execution.
        """
        if not self.allow_execute_code:
            raise Exception("execute_code is disabled. Tick 'Allow execute_code' in the QGIS MCP dock to enable it.")

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        namespace = {
            "qgis": Qgis,
            "QgsProject": QgsProject,
            "iface": self.iface,
            "QgsApplication": QgsApplication,
            "QgsVectorLayer": QgsVectorLayer,
            "QgsRasterLayer": QgsRasterLayer,
            "QgsCoordinateReferenceSystem": QgsCoordinateReferenceSystem,
        }

        try:
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                exec(code, namespace)
        except Exception as e:
            return {
                "executed": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
            }
        return {"executed": True, "stdout": stdout_capture.getvalue(), "stderr": stderr_capture.getvalue()}

    def add_vector_layer(self, path, name=None, provider="ogr", **kwargs):
        """Add a vector layer to the project"""
        if not name:
            name = os.path.basename(path)

        # Create the layer
        layer = QgsVectorLayer(path, name, provider)

        if not layer.isValid():
            raise Exception(f"Layer is not valid: {path}")

        # Add to project
        QgsProject.instance().addMapLayer(layer)

        return {
            "id": layer.id(),
            "name": layer.name(),
            "type": self._get_layer_type(layer),
            "feature_count": layer.featureCount(),
        }

    def add_raster_layer(self, path, name=None, provider="gdal", **kwargs):
        """Add a raster layer to the project"""
        if not name:
            name = os.path.basename(path)

        # Create the layer
        layer = QgsRasterLayer(path, name, provider)

        if not layer.isValid():
            raise Exception(f"Layer is not valid: {path}")

        # Add to project
        QgsProject.instance().addMapLayer(layer)

        return {
            "id": layer.id(),
            "name": layer.name(),
            "type": "raster",
            "width": layer.width(),
            "height": layer.height(),
        }

    def list_layers(self, **kwargs):
        """Get all layers with rich metadata"""
        project = QgsProject.instance()
        layers = []

        for layer_id, layer in project.mapLayers().items():
            tree_node = project.layerTreeRoot().findLayer(layer_id)
            layer_info = {
                "id": layer_id,
                "name": layer.name(),
                "type": "vector"
                if layer.type() == QgsMapLayer.VectorLayer
                else ("raster" if layer.type() == QgsMapLayer.RasterLayer else str(layer.type())),
                "visible": tree_node.isVisible() if tree_node else False,
                "crs": layer.crs().authid() if layer.crs().isValid() else "Unknown",
            }

            if layer.type() == QgsMapLayer.VectorLayer:
                layer_info.update(
                    {
                        "geometry_type": self._geometry_type_name(layer),
                        "feature_count": layer.featureCount(),
                        "fields": [{"name": f.name(), "type": f.typeName()} for f in layer.fields()],
                    }
                )
            elif layer.type() == QgsMapLayer.RasterLayer:
                layer_info.update(
                    {
                        "band_count": layer.bandCount(),
                        "width": layer.width(),
                        "height": layer.height(),
                        "pixel_size": {
                            "x": layer.rasterUnitsPerPixelX(),
                            "y": layer.rasterUnitsPerPixelY(),
                        },
                    }
                )

            layers.append(layer_info)

        return layers

    def get_layer_fields(self, layer_name, **kwargs):
        """Get detailed field information for a vector layer"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)

        fields = []
        for f in layer.fields():
            fields.append(
                {
                    "name": f.name(),
                    "type": f.typeName(),
                    "length": f.length(),
                    "precision": f.precision(),
                    "comment": f.comment() or "",
                }
            )
        return {"layer_name": layer_name, "fields": fields}

    def _field_index(self, layer, field_name):
        """Return the index of a field, or raise with the field names on offer."""
        field_idx = layer.fields().indexOf(field_name)
        if field_idx < 0:
            available = [f.name() for f in layer.fields()]
            raise Exception(f"Field '{field_name}' not found in layer '{layer.name()}'. Available fields: {available}")
        return field_idx

    def _page_bounds(self, limit, offset):
        """Return the clamped page size and start index for a list result."""
        return (
            max(0, min(int(limit), self.MAX_FEATURES_PER_REQUEST)),
            max(0, int(offset)),
        )

    def _sorted_unique_values(self, layer, field_idx):
        """Return every distinct value of a field, sorted, with NULL removed.

        The provider does the distinct pass, so the whole layer is not read into
        Python.
        """
        values = [value for value in layer.uniqueValues(field_idx) if value is not None and value != NULL]
        return sorted(values, key=lambda x: (isinstance(x, str), x))

    def get_unique_values(self, layer_name, field_name, limit=50, offset=0, **kwargs):
        """Return one sorted page of the distinct values a field holds"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
        field_idx = self._field_index(layer, field_name)
        limit, offset = self._page_bounds(limit, offset)

        sorted_values = self._sorted_unique_values(layer, field_idx)
        page = sorted_values[offset : offset + limit]

        return {
            "layer_name": layer_name,
            "field_name": field_name,
            "total_count": len(sorted_values),
            "returned_count": len(page),
            "offset": offset,
            "has_more": offset + len(page) < len(sorted_values),
            "values": page,
        }

    def _feature_page(self, layer, limit, offset, expression=None):
        """Return one page of features, with WGS84 WKT geometry."""
        limit, offset = self._page_bounds(limit, offset)

        request = QgsFeatureRequest()
        if expression:
            expr = QgsExpression(expression)
            if expr.hasParserError():
                raise Exception(f"Invalid expression: {expr.parserErrorString()}")
            request.setFilterExpression(expression)

        wgs84 = self._wgs84_crs()
        xform = self._transform(layer.crs(), wgs84)
        field_names = [field.name() for field in layer.fields()]
        features = []
        seen = 0
        has_more = False
        for feature in layer.getFeatures(request):
            seen += 1
            if seen <= offset:
                continue
            if len(features) >= limit:
                has_more = True
                break

            attrs = {name: (None if value == NULL else value) for name, value in zip(field_names, feature.attributes())}

            geom_wkt = None
            if feature.hasGeometry():
                geometry = self._apply_transform(feature.geometry(), xform, layer.crs(), wgs84)
                geom_wkt = self._truncate_wkt(geometry.asWkt(precision=self.WKT_PRECISION))

            features.append({"id": feature.id(), "attributes": attrs, "geometry_wkt": geom_wkt})
            self._pump_ui()

        return {
            "layer_name": layer.name(),
            "total_count": layer.featureCount(),
            "returned_count": len(features),
            "offset": offset,
            "has_more": has_more,
            "features": features,
        }

    def sample_features(self, layer_name, count=5, expression=None, offset=0, **kwargs):
        """Sample features from a layer with optional expression filter"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
        return self._feature_page(layer, count, offset, expression)

    def get_layer_extent(self, layer_name, **kwargs):
        """Get layer bounding box in WGS84"""
        layer = self._resolve_layer(layer_name)
        extent = self._rect_to_wgs84(layer.extent(), layer.crs())

        return {
            "layer_name": layer_name,
            "xmin": extent.xMinimum(),
            "ymin": extent.yMinimum(),
            "xmax": extent.xMaximum(),
            "ymax": extent.yMaximum(),
        }

    def _copy_features_to(self, mem_layer, source_layer, features):
        """Write features into a memory layer in batches, reprojected to WGS84.

        Returns:
            The number of features written.
        """
        provider = mem_layer.dataProvider()
        source_crs = source_layer.crs()
        wgs84 = self._wgs84_crs()
        xform = self._transform(source_crs, wgs84)
        batch = []
        written = 0
        for feature in features:
            new_feature = QgsFeature(mem_layer.fields())
            new_feature.setAttributes(feature.attributes())
            if feature.hasGeometry():
                new_feature.setGeometry(self._apply_transform(feature.geometry(), xform, source_crs, wgs84))
            batch.append(new_feature)
            if len(batch) >= self.FEATURE_BATCH_SIZE:
                provider.addFeatures(batch)
                written += len(batch)
                batch = []
                self._pump_ui()
        if batch:
            provider.addFeatures(batch)
            written += len(batch)
        mem_layer.updateExtents()
        return written

    def filter_layer(self, layer_name, expression, output_name, **kwargs):
        """Create a new memory layer from features matching an expression"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)

        expr = QgsExpression(expression)
        if expr.hasParserError():
            raise Exception(f"Invalid expression: {expr.parserErrorString()}")

        mem_layer = self._create_wgs84_memory_layer(layer, output_name)
        request = QgsFeatureRequest().setFilterExpression(expression)
        written = self._copy_features_to(mem_layer, layer, layer.getFeatures(request))
        QgsProject.instance().addMapLayer(mem_layer)

        return {
            "output_name": output_name,
            "feature_count": written,
            "source_layer": layer_name,
            "expression": expression,
        }

    def _feature_by_field_value(self, layer, field_name, value):
        """Return the first feature whose field equals a value, or None.

        The lookup goes to the data provider as an expression, so a large layer
        is never read into Python.
        """
        expression = f"{QgsExpression.quotedColumnRef(field_name)} = {QgsExpression.quotedValue(value)}"
        request = QgsFeatureRequest().setFilterExpression(expression).setLimit(1)
        for feature in layer.getFeatures(request):
            return feature
        return None

    def _nearest_feature(self, layer, point):
        """Return the feature closest to a point in the layer's own CRS.

        The search starts in a small box around the point and doubles the box
        until it finds a feature.

        Raises:
            Exception: If no feature is found inside the whole layer extent.
        """
        extent = layer.extent()
        reach = max(extent.width(), extent.height()) or 1.0
        search = reach / 500.0
        target = QgsGeometry.fromPointXY(point)

        while search <= reach * 2:
            rect = QgsRectangle(point.x() - search, point.y() - search, point.x() + search, point.y() + search)
            nearest = None
            shortest = None
            for feature in layer.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
                if not feature.hasGeometry():
                    continue
                distance = feature.geometry().distance(target)
                if shortest is None or distance < shortest:
                    shortest, nearest = distance, feature
            if nearest is not None:
                return nearest
            search *= 2
            self._pump_ui()

        raise Exception("No features found near the start point")

    def trace_downstream(
        self,
        layer_name,
        start_lon,
        start_lat,
        id_field="HYRIV_ID",
        next_down_field="NEXT_DOWN",
        output_name="traced_river",
        **kwargs,
    ):
        """Trace a river network downstream from a point"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
        self._field_index(layer, id_field)
        self._field_index(layer, next_down_field)

        start_point = self._point_from_wgs84(QgsPointXY(start_lon, start_lat), layer.crs())

        segment = self._nearest_feature(layer, start_point)

        traced_ids = []
        traced = []
        visited = set()
        while segment is not None:
            current_id = segment.attribute(id_field)
            if current_id is None or current_id == NULL or current_id in visited:
                break
            if len(traced_ids) >= self.MAX_TRACE_SEGMENTS:
                raise Exception(
                    f"The trace passed {self.MAX_TRACE_SEGMENTS} segments. "
                    f"Check that '{next_down_field}' points downstream."
                )
            visited.add(current_id)
            traced_ids.append(current_id)
            traced.append(segment)

            next_id = segment.attribute(next_down_field)
            if next_id is None or next_id == NULL or next_id == 0:
                break
            segment = self._feature_by_field_value(layer, id_field, next_id)
            self._pump_ui()

        mem_layer = self._create_wgs84_memory_layer(layer, output_name)
        written = self._copy_features_to(mem_layer, layer, traced)
        QgsProject.instance().addMapLayer(mem_layer)

        return {
            "output_name": output_name,
            "segments_traced": written,
            "start_segment_id": traced_ids[0] if traced_ids else None,
            "end_segment_id": traced_ids[-1] if traced_ids else None,
        }

    def set_layer_visibility(self, layer_name, visible, **kwargs):
        """Set layer visibility"""
        layer = self._resolve_layer(layer_name)
        project = QgsProject.instance()
        tree_node = project.layerTreeRoot().findLayer(layer.id())
        if tree_node is None:
            raise Exception(f"Layer '{layer_name}' not found in layer tree")
        tree_node.setItemVisibilityChecked(visible)
        self.iface.mapCanvas().refresh()
        return {
            "layer_name": layer_name,
            "visible": visible,
        }

    def set_canvas_extent(self, xmin, ymin, xmax, ymax, **kwargs):
        """Set the map canvas extent from WGS84 coordinates"""
        rect = self._rect_from_wgs84(QgsRectangle(xmin, ymin, xmax, ymax), QgsProject.instance().crs())

        self.iface.mapCanvas().setExtent(rect)
        self.iface.mapCanvas().refresh()
        return {
            "extent": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
        }

    def style_line_graduated(
        self, layer_name, width_field, color="#1a5276", min_width=0.3, max_width=3.5, num_classes=0, **kwargs
    ):
        """Apply graduated line width styling based on a numeric field.

        The provider supplies the minimum and the maximum, so the whole layer is
        never read into Python. The classes are equal intervals.
        """
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
        field_idx = self._field_index(layer, width_field)

        try:
            min_val = float(layer.minimumValue(field_idx))
            max_val = float(layer.maximumValue(field_idx))
        except (TypeError, ValueError):
            raise Exception(f"No numeric values found in field '{width_field}'")

        if max_val <= min_val:
            raise Exception(f"Field '{width_field}' holds a single value ({min_val}), so it cannot be graduated.")

        num_classes = int(num_classes) if int(num_classes) > 0 else self.DEFAULT_GRADUATED_CLASSES

        ranges = []
        step = (max_val - min_val) / num_classes
        width_step = (max_width - min_width) / num_classes

        for i in range(num_classes):
            lower = min_val + (step * i)
            upper = min_val + (step * (i + 1))
            width = min_width + (width_step * (i + 0.5))
            label = f"{lower:.1f} - {upper:.1f}"

            symbol = QgsLineSymbol.createSimple(
                {
                    "color": color,
                    "width": str(width),
                    "capstyle": "round",
                    "joinstyle": "round",
                }
            )
            rng = QgsRendererRange(lower, upper, symbol, label)
            ranges.append(rng)

        renderer = QgsGraduatedSymbolRenderer(width_field, ranges)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

        return {
            "layer_name": layer_name,
            "field": width_field,
            "classes": num_classes,
            "value_range": {"min": min_val, "max": max_val},
            "width_range": {"min": min_width, "max": max_width},
        }

    def style_simple(self, layer_name, color="#333333", outline_color="#000000", width=0.5, opacity=1.0, **kwargs):
        """Apply simple single-symbol styling"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
        symbol = self._symbol_for(layer, color, outline_color=outline_color, width=width)

        from qgis.core import QgsSingleSymbolRenderer

        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.setOpacity(opacity)
        layer.triggerRepaint()

        return {
            "layer_name": layer_name,
            "color": color,
            "opacity": opacity,
        }

    def style_categorized(self, layer_name, field_name, color_ramp="Spectral", width=1.0, **kwargs):
        """Apply categorized styling using a color ramp"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
        field_idx = self._field_index(layer, field_name)

        unique_values = self._sorted_unique_values(layer, field_idx)
        if not unique_values:
            raise Exception(f"Field '{field_name}' holds no values, so it cannot be categorized.")

        style = QgsApplication.instance().styleManager() if hasattr(QgsApplication, "styleManager") else None
        ramp = None
        if style:
            ramp = style.colorRamp(color_ramp)
        if ramp is None:
            from qgis.core import QgsGradientColorRamp

            ramp = QgsGradientColorRamp(QColor("#d73027"), QColor("#1a9850"))

        categories = []
        num_values = len(unique_values)

        for index, value in enumerate(unique_values):
            category_color = ramp.color(index / max(num_values - 1, 1)).name()
            symbol = self._symbol_for(layer, category_color, outline_color="#333333", width=width)
            categories.append(QgsRendererCategory(value, symbol, str(value)))

        renderer = QgsCategorizedSymbolRenderer(field_name, categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

        return {
            "layer_name": layer_name,
            "field": field_name,
            "categories": num_values,
            "color_ramp": color_ramp,
        }

    def add_labels(
        self,
        layer_name,
        field_name,
        font_size=10,
        color="#1a1a1a",
        follow_line=True,
        buffer_size=1.0,
        font_family="Noto Sans",
        **kwargs,
    ):
        """Add labels to a layer"""
        layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
        self._field_index(layer, field_name)

        # Configure text format
        text_format = QgsTextFormat()
        text_format.setFont(QFont(font_family))
        text_format.setSize(font_size)
        text_format.setColor(QColor(color))

        # Buffer/halo
        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(buffer_size)
        buffer_settings.setColor(QColor(255, 255, 255))
        text_format.setBuffer(buffer_settings)

        # Label settings
        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = field_name
        label_settings.setFormat(text_format)

        # Line following
        if follow_line and layer.geometryType() == QgsWkbTypes.LineGeometry:
            label_settings.placement = QgsPalLayerSettings.Curved

        # Apply labeling
        labeling = QgsVectorLayerSimpleLabeling(label_settings)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

        return {
            "layer_name": layer_name,
            "field": field_name,
            "font_size": font_size,
            "follow_line": follow_line,
        }

    def _get_page_dimensions(self, page_size, orientation):
        """Return (width_mm, height_mm) for a given page size and orientation."""
        sizes = {
            "A3": (420, 297),
            "A4": (297, 210),
            "letter": (279.4, 215.9),
            "tabloid": (431.8, 279.4),
        }
        w, h = sizes.get(page_size, sizes["A3"])
        if orientation == "portrait":
            w, h = h, w
        return w, h

    def create_print_layout(self, name, page_size="A3", orientation="landscape", title=None, replace=False, **kwargs):
        """Create a print layout with map, scale bar, and north arrow.

        Raises:
            Exception: If a layout of this name exists and replace is false.
        """
        project = QgsProject.instance()
        manager = project.layoutManager()

        existing = manager.layoutByName(name)
        if existing:
            if not replace:
                raise Exception(f"A layout named '{name}' already exists. Pass replace=true to overwrite it.")
            manager.removeLayout(existing)

        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(name)

        # Set page size
        page_w, page_h = self._get_page_dimensions(page_size, orientation)
        page = layout.pageCollection().page(0)
        page.setPageSize(QgsLayoutSize(page_w, page_h, QgsUnitTypes.LayoutMillimeters))

        # Margins
        margin = 15  # mm

        # Calculate map area
        map_y = margin
        map_h = page_h - (2 * margin)
        if title:
            map_y = margin + 15  # leave room for title
            map_h = page_h - (2 * margin) - 15

        # Add map item
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(QRectF(0, 0, page_w - 2 * margin, map_h))
        map_item.attemptMove(QgsLayoutPoint(margin, map_y, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(page_w - 2 * margin, map_h, QgsUnitTypes.LayoutMillimeters))
        map_item.setExtent(self.iface.mapCanvas().extent())
        map_item.setId("main")
        layout.addLayoutItem(map_item)

        # Add title if provided
        if title:
            title_item = QgsLayoutItemLabel(layout)
            title_item.setText(title)
            title_font = QFont("Noto Sans", 18)
            title_font.setBold(True)
            title_item.setFont(title_font)
            title_item.setHAlign(Qt.AlignHCenter)
            title_item.attemptMove(QgsLayoutPoint(margin, margin, QgsUnitTypes.LayoutMillimeters))
            title_item.attemptResize(QgsLayoutSize(page_w - 2 * margin, 12, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(title_item)

        # Add scale bar
        scale_bar = QgsLayoutItemScaleBar(layout)
        scale_bar.setLinkedMap(map_item)
        scale_bar.setStyle("Single Box")
        scale_bar.setNumberOfSegments(4)
        scale_bar.setNumberOfSegmentsLeft(0)
        scale_bar.setUnitsPerSegment(50)
        scale_bar.applyDefaultSize()
        scale_bar.attemptMove(QgsLayoutPoint(margin, page_h - margin - 8, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(scale_bar)

        # Add north arrow
        north_arrow = QgsLayoutItemPicture(layout)
        svg_paths = QgsApplication.svgPaths()
        arrow_path = None
        for svg_dir in svg_paths:
            candidate = os.path.join(svg_dir, "arrows", "NorthArrow_02.svg")
            if os.path.exists(candidate):
                arrow_path = candidate
                break
        if arrow_path:
            north_arrow.setPicturePath(arrow_path)
        north_arrow.attemptResize(QgsLayoutSize(15, 15, QgsUnitTypes.LayoutMillimeters))
        north_arrow.attemptMove(
            QgsLayoutPoint(page_w - margin - 15, page_h - margin - 15, QgsUnitTypes.LayoutMillimeters)
        )
        layout.addLayoutItem(north_arrow)

        manager.addLayout(layout)

        return {
            "name": name,
            "page_size": page_size,
            "orientation": orientation,
            "dimensions_mm": {"width": page_w, "height": page_h},
            "has_title": title is not None,
        }

    def _find_layout(self, layout_name):
        """Return a print layout by name, or raise with the names on offer."""
        manager = QgsProject.instance().layoutManager()
        layout = manager.layoutByName(layout_name)
        if not layout:
            available = [item.name() for item in manager.layouts()]
            raise Exception(f"Layout '{layout_name}' not found. Available layouts: {available}")
        return layout

    def _main_map_item(self, layout):
        """Return the layout's main map item.

        The item with the id 'main' wins. A layout built by hand has no such id,
        so the first map item is used instead.

        Raises:
            Exception: If the layout holds no map item.
        """
        named = layout.itemById("main")
        if named is not None:
            return named
        for item in layout.items():
            if isinstance(item, QgsLayoutItemMap):
                return item
        raise Exception(f"Layout '{layout.name()}' holds no map item. Add a map to it first.")

    def add_legend(self, layout_name, title="Legend", position=None, width=45, layers=None, background=True, **kwargs):
        """Add a legend to a print layout"""
        if position is None:
            position = [15, 30]

        layout = self._find_layout(layout_name)
        map_item = self._main_map_item(layout)

        legend = QgsLayoutItemLegend(layout)
        legend.setLinkedMap(map_item)
        legend.setTitle(title)

        # Filter to specific layers if requested
        if layers:
            legend.setAutoUpdateModel(False)
            model = legend.model()
            root = model.rootGroup()
            # Remove layers not in the filter list
            for tree_layer in root.findLayers():
                if tree_layer.name() not in layers:
                    root.removeChildNode(tree_layer)

        # Background
        if background:
            legend.setBackgroundEnabled(True)
            legend.setBackgroundColor(QColor(255, 255, 255, 200))
            legend.setFrameEnabled(True)
            legend.setFrameStrokeColor(QColor(200, 200, 200))

        legend.attemptMove(QgsLayoutPoint(position[0], position[1], QgsUnitTypes.LayoutMillimeters))
        legend.attemptResize(QgsLayoutSize(width, 100, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)

        return {
            "layout_name": layout_name,
            "title": title,
            "position": position,
        }

    def add_inset_map(
        self, layout_name, extent, position=None, size=None, layers=None, show_extent_indicator=True, **kwargs
    ):
        """Add an inset/overview map to a print layout"""
        if position is None:
            position = [320, 15]
        if size is None:
            size = [80, 80]

        project = QgsProject.instance()
        layout = self._find_layout(layout_name)
        map_item = self._main_map_item(layout)

        # Create inset map
        inset = QgsLayoutItemMap(layout)
        inset.setId("inset")
        inset.attemptMove(QgsLayoutPoint(position[0], position[1], QgsUnitTypes.LayoutMillimeters))
        inset.attemptResize(QgsLayoutSize(size[0], size[1], QgsUnitTypes.LayoutMillimeters))

        # Set extent (reproject from WGS84 if needed)
        inset.setExtent(self._rect_from_wgs84(QgsRectangle(*extent), project.crs()))

        # Filter layers if specified
        if layers:
            layer_objects = []
            for lname in layers:
                with contextlib.suppress(Exception):
                    layer_objects.append(self._resolve_layer(lname))
            if layer_objects:
                inset.setLayers(layer_objects)
                inset.setKeepLayerSet(True)

        # Frame styling
        inset.setFrameEnabled(True)
        inset.setFrameStrokeColor(QColor(0, 0, 0))
        inset.setFrameStrokeWidth(QgsLayoutMeasurement(0.5, QgsUnitTypes.LayoutMillimeters))

        layout.addLayoutItem(inset)

        # Add extent indicator (overview) showing main map extent on inset
        if show_extent_indicator:
            overview = inset.overviews()
            overview.addOverview(QgsLayoutItemMapOverview("Main extent", inset))
            ov = overview.overview(0)
            ov.setLinkedMap(map_item)
            ov.setFrameSymbol(
                QgsFillSymbol.createSimple(
                    {
                        "color": "255,0,0,40",
                        "outline_color": "255,0,0",
                        "outline_width": "0.5",
                    }
                )
            )
            ov.setEnabled(True)

        return {
            "layout_name": layout_name,
            "position": position,
            "size": size,
            "extent": extent,
            "show_extent_indicator": show_extent_indicator,
        }

    def export_layout(self, layout_name, output_path, dpi=300, **kwargs):
        """Export a print layout to PDF or image"""
        layout = self._find_layout(layout_name)
        exporter = QgsLayoutExporter(layout)
        ext = os.path.splitext(output_path)[1].lower()

        if ext == ".pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            settings.dpi = dpi
            result = exporter.exportToPdf(output_path, settings)
        else:
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = dpi
            result = exporter.exportToImage(output_path, settings)

        if result != QgsLayoutExporter.Success:
            error_map = {
                QgsLayoutExporter.FileError: "File error",
                QgsLayoutExporter.MemoryError: "Memory error",
                QgsLayoutExporter.SvgLayerError: "SVG layer error",
                QgsLayoutExporter.PrintError: "Print error",
            }
            error_msg = error_map.get(result, f"Unknown error (code {result})")
            raise Exception(f"Export failed: {error_msg}")

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

        return {
            "output_path": output_path,
            "format": ext.lstrip("."),
            "dpi": dpi,
            "file_size_bytes": file_size,
        }

    def remove_layer(self, layer, **kwargs):
        """Remove a layer from the project, by its name or its id.

        The project deletes the layer object, so the id and the name are read
        before the removal.
        """
        found = self._resolve_layer(layer)
        layer_id = found.id()
        layer_name = found.name()
        QgsProject.instance().removeMapLayer(layer_id)
        return {"removed": layer_id, "name": layer_name}

    def zoom_to_layer(self, layer, **kwargs):
        """Zoom to a layer's extent, by its name or its id"""
        found = self._resolve_layer(layer)
        self.iface.setActiveLayer(found)
        self.iface.zoomToActiveLayer()
        return {"zoomed_to": found.id(), "name": found.name()}

    def get_layer_features(self, layer, limit=10, offset=0, **kwargs):
        """Read one page of features from a vector layer, by its name or its id"""
        found = self._resolve_layer(layer)
        self._require_vector(found, layer)
        return self._feature_page(found, limit, offset)

    def _describe_processing_output(self, value):
        """Return a processing output that a later tool can use.

        A layer output keeps its id and name. Anything else becomes a string.
        """
        if isinstance(value, QgsMapLayer):
            return {"type": "layer", "id": value.id(), "name": value.name()}
        return str(value)

    def execute_processing(self, algorithm, parameters, **kwargs):
        """Execute a processing algorithm"""
        try:
            import processing

            result = processing.run(algorithm, parameters)
        except Exception as e:
            raise Exception(f"Processing error: {str(e)}")
        return {
            "algorithm": algorithm,
            "result": {key: self._describe_processing_output(value) for key, value in result.items()},
        }

    def save_project(self, path=None, **kwargs):
        """Save the current project"""
        project = QgsProject.instance()

        if not path and not project.fileName():
            raise Exception("No project path specified and no current project path")

        save_path = path if path else project.fileName()
        if project.write(save_path):
            return {"saved": save_path}
        else:
            raise Exception(f"Failed to save project to {save_path}")

    def load_project(self, path, **kwargs):
        """Load a project"""
        project = QgsProject.instance()

        if project.read(path):
            self.iface.mapCanvas().refresh()
            return {"loaded": path, "layer_count": len(project.mapLayers())}
        else:
            raise Exception(f"Failed to load project from {path}")

    def create_new_project(self, path, **kwargs):
        """
        Creates a new QGIS project and saves it at the specified path.
        If a project is already loaded, it clears it before creating the new one.

        :param path: Full path where the project will be saved
                     (e.g., 'C:/path/to/project.qgz')
        """
        project = QgsProject.instance()

        if project.fileName():
            project.clear()

        project.setFileName(path)
        self.iface.mapCanvas().refresh()

        # Save the project
        if project.write():
            return {
                "created": f"Project created and saved successfully at: {path}",
                "layer_count": len(project.mapLayers()),
            }
        else:
            raise Exception(f"Failed to save project to {path}")

    def render_map(self, path, width=800, height=600, **kwargs):
        """Render the current map view to an image.

        The image uses the canvas layer set, so it matches what the user sees.
        """
        try:
            # Create map settings
            ms = QgsMapSettings()

            # Set layers to render
            ms.setLayers(self.iface.mapCanvas().layers())

            # Set map canvas properties
            rect = self.iface.mapCanvas().extent()
            ms.setExtent(rect)
            ms.setOutputSize(QSize(width, height))
            ms.setBackgroundColor(QColor(255, 255, 255))
            ms.setOutputDpi(96)

            # Create the render
            render = QgsMapRendererParallelJob(ms)

            # Start rendering
            render.start()
            render.waitForFinished()

            # Get the image and save
            img = render.renderedImage()
            if img.save(path):
                return {"rendered": True, "path": path, "width": width, "height": height}
            else:
                raise Exception(f"Failed to save rendered image to {path}")

        except Exception as e:
            raise Exception(f"Render error: {str(e)}")


class QgisMCPDockWidget(QDockWidget):
    """Dock widget for the QGIS MCP plugin"""

    closed = pyqtSignal()

    def __init__(self, iface):
        super().__init__("QGIS MCP")
        self.iface = iface
        self.server = None
        self.setup_ui()

    def setup_ui(self):
        """Set up the dock widget UI"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        layout.addWidget(QLabel("Server Port (bound to 127.0.0.1):"))
        self.port_spin = QSpinBox()
        self.port_spin.setMinimum(1024)
        self.port_spin.setMaximum(65535)
        self.port_spin.setValue(9876)
        layout.addWidget(self.port_spin)

        self.execute_code_check = QCheckBox("Allow execute_code (runs arbitrary Python)")
        self.execute_code_check.setChecked(False)
        self.execute_code_check.toggled.connect(self.on_execute_code_toggled)
        layout.addWidget(self.execute_code_check)

        self.start_button = QPushButton("Start Server")
        self.start_button.clicked.connect(self.start_server)
        layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Server")
        self.stop_button.clicked.connect(self.stop_server)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        self.status_label = QLabel("Server: Stopped")
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Token (the client usually finds this by itself):"))
        self.token_field = QLineEdit()
        self.token_field.setReadOnly(True)
        self.token_field.setPlaceholderText("Start the server to generate a token")
        layout.addWidget(self.token_field)

        self.copy_button = QPushButton("Copy Token")
        self.copy_button.clicked.connect(self.copy_token)
        self.copy_button.setEnabled(False)
        layout.addWidget(self.copy_button)

        self.setWidget(widget)

    def on_execute_code_toggled(self, checked):
        """Apply the execute_code opt-in to a running server."""
        if self.server:
            self.server.allow_execute_code = checked

    def copy_token(self):
        """Put the current token on the clipboard."""
        if not self.server:
            return
        QApplication.clipboard().setText(self.server.token)
        self.status_label.setText("Token copied to the clipboard.")

    def start_server(self):
        """Start the server"""
        if not self.server:
            self.server = QgisMCPServer(
                port=self.port_spin.value(),
                iface=self.iface,
                allow_execute_code=self.execute_code_check.isChecked(),
            )

        if self.server.start():
            self.status_label.setText(f"Server: Running on 127.0.0.1:{self.server.port}")
            self.token_field.setText(self.server.token)
            self.copy_button.setEnabled(True)
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.port_spin.setEnabled(False)
        else:
            self.server = None
            self.status_label.setText("Server: Failed to start. See the QGIS MCP log for the reason.")

    def stop_server(self):
        """Stop the server"""
        if self.server:
            self.server.stop()
            self.server = None

        self.status_label.setText("Server: Stopped")
        self.token_field.clear()
        self.copy_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.port_spin.setEnabled(True)

    def closeEvent(self, event):
        """Stop server on dock close"""
        self.stop_server()
        self.closed.emit()
        super().closeEvent(event)


class QgisMCPPlugin:
    """Main plugin class for QGIS MCP"""

    def __init__(self, iface):
        self.iface = iface
        self.dock_widget = None
        self.action = None

    def initGui(self):
        """Initialize GUI"""
        # Create action
        self.action = QAction("QGIS MCP", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_dock)

        # Add to plugins menu and toolbar
        self.iface.addPluginToMenu("QGIS MCP", self.action)
        self.iface.addToolBarIcon(self.action)

    def toggle_dock(self, checked):
        """Toggle the dock widget"""
        if checked:
            # Create dock widget if it doesn't exist
            if not self.dock_widget:
                self.dock_widget = QgisMCPDockWidget(self.iface)
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
                # Connect close event
                self.dock_widget.closed.connect(self.dock_closed)
            else:
                # Show existing dock widget
                self.dock_widget.show()
        else:
            # Hide dock widget
            if self.dock_widget:
                self.dock_widget.hide()

    def dock_closed(self):
        """Handle dock widget closed"""
        self.action.setChecked(False)

    def unload(self):
        """Unload plugin"""
        # Stop server if running
        if self.dock_widget:
            self.dock_widget.stop_server()
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget = None

        # Remove plugin menu item and toolbar icon
        self.iface.removePluginMenu("QGIS MCP", self.action)
        self.iface.removeToolBarIcon(self.action)


# Plugin entry point
def classFactory(iface):
    return QgisMCPPlugin(iface)
