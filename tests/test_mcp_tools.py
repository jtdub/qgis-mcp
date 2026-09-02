"""Tests for all 32 MCP tool functions.

Each tool calls _call, which sends the command and returns the result payload.
Tests verify the command type, the parameters, and the error mapping.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from qgis_mcp import qgis_mcp_server as mod


@pytest.fixture
def mock_conn():
    """Patch get_qgis_connection and return the mock connection."""
    with patch.object(mod, "get_qgis_connection") as mock_get:
        conn = MagicMock()
        conn.send_command.return_value = {"status": "success", "result": {}}
        mock_get.return_value = conn
        yield conn


def assert_one_command(conn, command, params=None):
    """Check that exactly one command went to QGIS, with these parameters."""
    conn.send_command.assert_called_once()
    assert conn.send_command.call_args[0][:2] == (command, params if params is not None else {})


# --- Group 1: Simple tools ---


@pytest.mark.parametrize(
    "func_name,command_type",
    [
        ("ping", "ping"),
        ("get_project_info", "get_project_info"),
        ("list_layers", "list_layers"),
    ],
)
async def test_simple_tools(func_name, command_type, mock_ctx, mock_conn):
    func = getattr(mod, func_name)
    result = await func()

    assert_one_command(mock_conn, command_type, {})
    assert result == {}


# --- Group 2: Tools with required params only ---


async def test_get_qgis_info_adds_the_server_version(mock_conn):
    mock_conn.send_command.return_value = {"status": "success", "result": {"qgis_version": "3.34.8"}}

    result = await mod.get_qgis_info()

    assert_one_command(mock_conn, "get_qgis_info", {})
    assert result["qgis_version"] == "3.34.8"
    assert result["server_version"] == mod.__version__


async def test_load_project(mock_ctx, mock_conn):
    await mod.load_project(path="/tmp/test.qgz")
    assert_one_command(mock_conn, "load_project", {"path": "/tmp/test.qgz"})


async def test_create_new_project(mock_ctx, mock_conn):
    await mod.create_new_project(path="/tmp/new.qgz")
    assert_one_command(mock_conn, "create_new_project", {"path": "/tmp/new.qgz"})


async def test_remove_layer_accepts_a_name(mock_ctx, mock_conn):
    await mod.remove_layer(layer="rivers")
    assert_one_command(mock_conn, "remove_layer", {"layer": "rivers"})


async def test_remove_layer_accepts_an_id(mock_ctx, mock_conn):
    await mod.remove_layer(layer="layer_123")
    assert_one_command(mock_conn, "remove_layer", {"layer": "layer_123"})


async def test_zoom_to_layer(mock_ctx, mock_conn):
    await mod.zoom_to_layer(layer="layer_123")
    assert_one_command(mock_conn, "zoom_to_layer", {"layer": "layer_123"})


async def test_get_layer_fields(mock_ctx, mock_conn):
    await mod.get_layer_fields(layer_name="rivers")
    assert_one_command(mock_conn, "get_layer_fields", {"layer_name": "rivers"})


async def test_get_layer_extent(mock_ctx, mock_conn):
    await mod.get_layer_extent(layer_name="rivers")
    assert_one_command(mock_conn, "get_layer_extent", {"layer_name": "rivers"})


async def test_execute_code(mock_conn):
    await mod.execute_code(code="print('hello')")
    assert mock_conn.send_command.call_args_list[-1][0][:2] == ("execute_code", {"code": "print('hello')"})


# --- Group 3: Tools with optional params ---


async def test_add_vector_layer_with_name(mock_ctx, mock_conn):
    await mod.add_vector_layer(path="/data/test.shp", provider="ogr", name="my_layer")
    assert_one_command(mock_conn, "add_vector_layer", {"path": "/data/test.shp", "provider": "ogr", "name": "my_layer"})


async def test_add_vector_layer_without_name(mock_ctx, mock_conn):
    await mod.add_vector_layer(path="/data/test.shp")
    assert_one_command(mock_conn, "add_vector_layer", {"path": "/data/test.shp", "provider": "ogr"})


async def test_add_raster_layer_with_name(mock_ctx, mock_conn):
    await mod.add_raster_layer(path="/data/test.tif", provider="gdal", name="dem")
    assert_one_command(mock_conn, "add_raster_layer", {"path": "/data/test.tif", "provider": "gdal", "name": "dem"})


async def test_add_raster_layer_without_name(mock_ctx, mock_conn):
    await mod.add_raster_layer(path="/data/test.tif")
    assert_one_command(mock_conn, "add_raster_layer", {"path": "/data/test.tif", "provider": "gdal"})


async def test_save_project_with_path(mock_ctx, mock_conn):
    await mod.save_project(path="/tmp/save.qgz")
    assert_one_command(mock_conn, "save_project", {"path": "/tmp/save.qgz"})


async def test_save_project_without_path(mock_ctx, mock_conn):
    await mod.save_project()
    assert_one_command(mock_conn, "save_project", {})


async def test_sample_features_with_expression(mock_ctx, mock_conn):
    await mod.sample_features(layer_name="rivers", count=3, expression="\"name\" = 'Nile'")
    assert_one_command(
        mock_conn,
        "sample_features",
        {"layer_name": "rivers", "count": 3, "expression": "\"name\" = 'Nile'", "offset": 0},
    )


async def test_sample_features_without_expression(mock_ctx, mock_conn):
    await mod.sample_features(layer_name="rivers")
    assert_one_command(mock_conn, "sample_features", {"layer_name": "rivers", "count": 5, "offset": 0})


async def test_create_print_layout_with_title(mock_ctx, mock_conn):
    await mod.create_print_layout(name="Map1", title="My Map")
    assert_one_command(
        mock_conn,
        "create_print_layout",
        {"name": "Map1", "page_size": "A3", "orientation": "landscape", "title": "My Map", "replace": False},
    )


async def test_create_print_layout_without_title(mock_ctx, mock_conn):
    await mod.create_print_layout(name="Map1")
    assert_one_command(
        mock_conn,
        "create_print_layout",
        {"name": "Map1", "page_size": "A3", "orientation": "landscape", "replace": False},
    )


async def test_add_legend_with_layers(mock_ctx, mock_conn):
    await mod.add_legend(layout_name="Map1", layers=["rivers", "cities"])
    assert_one_command(
        mock_conn,
        "add_legend",
        {"layout_name": "Map1", "title": "Legend", "width": 45, "background": True, "layers": ["rivers", "cities"]},
    )


async def test_add_legend_defaults(mock_ctx, mock_conn):
    await mod.add_legend(layout_name="Map1")
    assert_one_command(
        mock_conn, "add_legend", {"layout_name": "Map1", "title": "Legend", "width": 45, "background": True}
    )


async def test_add_inset_map_with_options(mock_conn):
    await mod.add_inset_map(
        layout_name="Map1", extent=[-80, -20, -60, 0], position=[300, 10], size=[60, 60], layers=["countries"]
    )
    assert_one_command(
        mock_conn,
        "add_inset_map",
        {
            "layout_name": "Map1",
            "extent": [-80, -20, -60, 0],
            "show_extent_indicator": True,
            "position": [300, 10],
            "size": [60, 60],
            "layers": ["countries"],
        },
    )


async def test_add_inset_map_defaults(mock_ctx, mock_conn):
    await mod.add_inset_map(layout_name="Map1", extent=[-80, -20, -60, 0])
    assert_one_command(
        mock_conn, "add_inset_map", {"layout_name": "Map1", "extent": [-80, -20, -60, 0], "show_extent_indicator": True}
    )


# --- Group 4: Tools with all required params ---


async def test_get_layer_features(mock_ctx, mock_conn):
    await mod.get_layer_features(layer="layer_123", limit=20)
    assert_one_command(mock_conn, "get_layer_features", {"layer": "layer_123", "limit": 20, "offset": 0})


async def test_execute_processing(mock_ctx, mock_conn):
    params = {"INPUT": "layer_123", "OUTPUT": "memory:"}
    await mod.execute_processing(algorithm="native:buffer", parameters=params)
    assert_one_command(mock_conn, "execute_processing", {"algorithm": "native:buffer", "parameters": params})


async def test_render_map(mock_ctx, mock_conn):
    await mod.render_map(mock_ctx, path="/tmp/map.png", width=1024, height=768)
    assert_one_command(mock_conn, "render_map", {"path": "/tmp/map.png", "width": 1024, "height": 768})


async def test_get_unique_values(mock_ctx, mock_conn):
    await mod.get_unique_values(layer_name="rivers", field_name="name", limit=25)
    assert_one_command(
        mock_conn, "get_unique_values", {"layer_name": "rivers", "field_name": "name", "limit": 25, "offset": 0}
    )


async def test_filter_layer(mock_ctx, mock_conn):
    await mod.filter_layer(mock_ctx, layer_name="rivers", expression='"order" > 3', output_name="big_rivers")
    assert_one_command(
        mock_conn, "filter_layer", {"layer_name": "rivers", "expression": '"order" > 3', "output_name": "big_rivers"}
    )


async def test_trace_downstream(mock_ctx, mock_conn):
    await mod.trace_downstream(
        mock_ctx,
        layer_name="hydro",
        start_lon=-72.0,
        start_lat=-13.5,
        id_field="HYRIV_ID",
        next_down_field="NEXT_DOWN",
        output_name="trace",
    )
    assert_one_command(
        mock_conn,
        "trace_downstream",
        {
            "layer_name": "hydro",
            "start_lon": -72.0,
            "start_lat": -13.5,
            "id_field": "HYRIV_ID",
            "next_down_field": "NEXT_DOWN",
            "output_name": "trace",
        },
    )


async def test_set_layer_visibility(mock_ctx, mock_conn):
    await mod.set_layer_visibility(layer_name="rivers", visible=False)
    assert_one_command(mock_conn, "set_layer_visibility", {"layer_name": "rivers", "visible": False})


async def test_set_canvas_extent(mock_ctx, mock_conn):
    await mod.set_canvas_extent(xmin=-72, ymin=-14, xmax=-70, ymax=-13)
    assert_one_command(mock_conn, "set_canvas_extent", {"xmin": -72, "ymin": -14, "xmax": -70, "ymax": -13})


async def test_style_line_graduated(mock_ctx, mock_conn):
    await mod.style_line_graduated(layer_name="rivers", width_field="ORD_STRA")
    assert_one_command(
        mock_conn,
        "style_line_graduated",
        {
            "layer_name": "rivers",
            "width_field": "ORD_STRA",
            "color": "#1a5276",
            "min_width": 0.3,
            "max_width": 3.5,
            "num_classes": 0,
        },
    )


async def test_style_simple(mock_ctx, mock_conn):
    await mod.style_simple(layer_name="rivers", color="#0000ff", opacity=0.8)
    assert_one_command(
        mock_conn,
        "style_simple",
        {"layer_name": "rivers", "color": "#0000ff", "outline_color": "#000000", "width": 0.5, "opacity": 0.8},
    )


async def test_style_categorized(mock_ctx, mock_conn):
    await mod.style_categorized(layer_name="rivers", field_name="type")
    assert_one_command(
        mock_conn,
        "style_categorized",
        {"layer_name": "rivers", "field_name": "type", "color_ramp": "Spectral", "width": 1.0},
    )


async def test_add_labels(mock_ctx, mock_conn):
    await mod.add_labels(layer_name="rivers", field_name="name")
    assert_one_command(
        mock_conn,
        "add_labels",
        {
            "layer_name": "rivers",
            "field_name": "name",
            "font_size": 10,
            "color": "#1a1a1a",
            "follow_line": True,
            "buffer_size": 1.0,
            "font_family": "Noto Sans",
        },
    )


async def test_export_layout(mock_ctx, mock_conn):
    await mod.export_layout(mock_ctx, layout_name="Map1", output_path="/tmp/map.pdf", dpi=150)
    assert_one_command(mock_conn, "export_layout", {"layout_name": "Map1", "output_path": "/tmp/map.pdf", "dpi": 150})


# --- JSON serialization ---


async def test_tool_returns_the_result_payload_as_compact_json(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "success", "result": {"key": "value"}}
    result = await mod.load_project(path="/tmp/a.qgz")
    assert isinstance(result, str)
    assert result == '{"key":"value"}'
    assert json.loads(result)["key"] == "value"


async def test_a_typed_tool_returns_the_result_payload_itself(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "success", "result": {"key": "value"}}
    assert await mod.ping() == {"key": "value"}


async def test_error_status_raises_tool_error(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "error", "message": "Layer 'x' not found."}
    with pytest.raises(ToolError, match="Layer 'x' not found."):
        await mod.list_layers()


async def test_error_status_without_message_still_raises(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "error"}
    with pytest.raises(ToolError, match="list_layers"):
        await mod.list_layers()


async def test_none_params_are_dropped_before_sending(mock_ctx, mock_conn):
    await mod.add_vector_layer(path="/tmp/a.shp")
    assert_one_command(mock_conn, "add_vector_layer", {"path": "/tmp/a.shp", "provider": "ogr"})


async def test_empty_string_path_is_sent_not_dropped(mock_ctx, mock_conn):
    await mod.save_project(path="")
    assert_one_command(mock_conn, "save_project", {"path": ""})


async def test_execute_code_raises_when_the_code_failed(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {
        "status": "success",
        "result": {"executed": False, "error": "boom", "traceback": "Traceback: boom"},
    }
    with pytest.raises(ToolError, match="Traceback: boom"):
        await mod.execute_code(code="raise RuntimeError('boom')")


async def test_execute_code_returns_output_on_success(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {
        "status": "success",
        "result": {"executed": True, "stdout": "hi", "stderr": ""},
    }
    assert json.loads(await mod.execute_code(code="print('hi')"))["stdout"] == "hi"


class TestStaleTokenRecovery:
    async def test_rejected_token_triggers_one_reconnect_and_retry(self, mock_ctx):
        stale = {"status": "error", "code": "unauthenticated", "message": "Authentication failed."}
        fresh = {"status": "success", "result": {"pong": True}}
        first, second = MagicMock(), MagicMock()
        first.send_command.return_value = stale
        second.send_command.return_value = fresh

        with patch.object(mod, "get_qgis_connection", side_effect=[first, second]) as mock_get:
            result = await mod.ping()

        assert result == {"pong": True}
        assert mock_get.call_count == 2
        assert_one_command(first, "ping", {})
        assert_one_command(second, "ping", {})

    async def test_a_second_rejection_raises(self, mock_ctx):
        stale = {"status": "error", "code": "unauthenticated", "message": "Authentication failed."}
        conn = MagicMock()
        conn.send_command.return_value = stale

        with (
            patch.object(mod, "get_qgis_connection", return_value=conn),
            pytest.raises(ToolError, match="Authentication failed."),
        ):
            await mod.ping()

        assert conn.send_command.call_count == 2
