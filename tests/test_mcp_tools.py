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


# --- Group 1: Simple tools (no params beyond ctx) ---


@pytest.mark.parametrize(
    "func_name,command_type",
    [
        ("ping", "ping"),
        ("get_qgis_info", "get_qgis_info"),
        ("get_project_info", "get_project_info"),
        ("list_layers", "list_layers"),
    ],
)
async def test_simple_tools(func_name, command_type, mock_ctx, mock_conn):
    func = getattr(mod, func_name)
    result = await func(mock_ctx)

    mock_conn.send_command.assert_called_once_with(command_type, {})
    assert result == {}


# --- Group 2: Tools with required params only ---


async def test_load_project(mock_ctx, mock_conn):
    await mod.load_project(mock_ctx, path="/tmp/test.qgz")
    mock_conn.send_command.assert_called_once_with("load_project", {"path": "/tmp/test.qgz"})


async def test_create_new_project(mock_ctx, mock_conn):
    await mod.create_new_project(mock_ctx, path="/tmp/new.qgz")
    mock_conn.send_command.assert_called_once_with("create_new_project", {"path": "/tmp/new.qgz"})


async def test_remove_layer_accepts_a_name(mock_ctx, mock_conn):
    await mod.remove_layer(mock_ctx, layer="rivers")
    mock_conn.send_command.assert_called_once_with("remove_layer", {"layer": "rivers"})


async def test_remove_layer_accepts_an_id(mock_ctx, mock_conn):
    await mod.remove_layer(mock_ctx, layer="layer_123")
    mock_conn.send_command.assert_called_once_with("remove_layer", {"layer": "layer_123"})


async def test_zoom_to_layer(mock_ctx, mock_conn):
    await mod.zoom_to_layer(mock_ctx, layer="layer_123")
    mock_conn.send_command.assert_called_once_with("zoom_to_layer", {"layer": "layer_123"})


async def test_get_layer_fields(mock_ctx, mock_conn):
    await mod.get_layer_fields(mock_ctx, layer_name="rivers")
    mock_conn.send_command.assert_called_once_with("get_layer_fields", {"layer_name": "rivers"})


async def test_get_layer_extent(mock_ctx, mock_conn):
    await mod.get_layer_extent(mock_ctx, layer_name="rivers")
    mock_conn.send_command.assert_called_once_with("get_layer_extent", {"layer_name": "rivers"})


async def test_execute_code(mock_ctx, mock_conn):
    await mod.execute_code(mock_ctx, code="print('hello')")
    assert mock_conn.send_command.call_args_list[-1][0] == ("execute_code", {"code": "print('hello')"})


async def test_execute_code_is_refused_when_the_dock_disallows_it(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "success", "result": {"execute_code_enabled": False}}
    with pytest.raises(ToolError, match="execute_code is disabled"):
        await mod.execute_code(mock_ctx, code="print('hello')")
    mock_conn.send_command.assert_called_once_with("ping", {})


# --- Group 3: Tools with optional params ---


async def test_add_vector_layer_with_name(mock_ctx, mock_conn):
    await mod.add_vector_layer(mock_ctx, path="/data/test.shp", provider="ogr", name="my_layer")
    mock_conn.send_command.assert_called_once_with(
        "add_vector_layer", {"path": "/data/test.shp", "provider": "ogr", "name": "my_layer"}
    )


async def test_add_vector_layer_without_name(mock_ctx, mock_conn):
    await mod.add_vector_layer(mock_ctx, path="/data/test.shp")
    mock_conn.send_command.assert_called_once_with("add_vector_layer", {"path": "/data/test.shp", "provider": "ogr"})


async def test_add_raster_layer_with_name(mock_ctx, mock_conn):
    await mod.add_raster_layer(mock_ctx, path="/data/test.tif", provider="gdal", name="dem")
    mock_conn.send_command.assert_called_once_with(
        "add_raster_layer", {"path": "/data/test.tif", "provider": "gdal", "name": "dem"}
    )


async def test_add_raster_layer_without_name(mock_ctx, mock_conn):
    await mod.add_raster_layer(mock_ctx, path="/data/test.tif")
    mock_conn.send_command.assert_called_once_with("add_raster_layer", {"path": "/data/test.tif", "provider": "gdal"})


async def test_save_project_with_path(mock_ctx, mock_conn):
    await mod.save_project(mock_ctx, path="/tmp/save.qgz")
    mock_conn.send_command.assert_called_once_with("save_project", {"path": "/tmp/save.qgz"})


async def test_save_project_without_path(mock_ctx, mock_conn):
    await mod.save_project(mock_ctx)
    mock_conn.send_command.assert_called_once_with("save_project", {})


async def test_sample_features_with_expression(mock_ctx, mock_conn):
    await mod.sample_features(mock_ctx, layer_name="rivers", count=3, expression="\"name\" = 'Nile'")
    mock_conn.send_command.assert_called_once_with(
        "sample_features", {"layer_name": "rivers", "count": 3, "expression": "\"name\" = 'Nile'", "offset": 0}
    )


async def test_sample_features_without_expression(mock_ctx, mock_conn):
    await mod.sample_features(mock_ctx, layer_name="rivers")
    mock_conn.send_command.assert_called_once_with("sample_features", {"layer_name": "rivers", "count": 5, "offset": 0})


async def test_create_print_layout_with_title(mock_ctx, mock_conn):
    await mod.create_print_layout(mock_ctx, name="Map1", title="My Map")
    mock_conn.send_command.assert_called_once_with(
        "create_print_layout",
        {"name": "Map1", "page_size": "A3", "orientation": "landscape", "title": "My Map", "replace": False},
    )


async def test_create_print_layout_without_title(mock_ctx, mock_conn):
    await mod.create_print_layout(mock_ctx, name="Map1")
    mock_conn.send_command.assert_called_once_with(
        "create_print_layout", {"name": "Map1", "page_size": "A3", "orientation": "landscape", "replace": False}
    )


async def test_add_legend_with_layers(mock_ctx, mock_conn):
    await mod.add_legend(mock_ctx, layout_name="Map1", layers=["rivers", "cities"])
    mock_conn.send_command.assert_called_once_with(
        "add_legend",
        {"layout_name": "Map1", "title": "Legend", "width": 45, "background": True, "layers": ["rivers", "cities"]},
    )


async def test_add_legend_defaults(mock_ctx, mock_conn):
    await mod.add_legend(mock_ctx, layout_name="Map1")
    mock_conn.send_command.assert_called_once_with(
        "add_legend", {"layout_name": "Map1", "title": "Legend", "width": 45, "background": True}
    )


async def test_add_inset_map_with_options(mock_ctx, mock_conn):
    await mod.add_inset_map(
        mock_ctx, layout_name="Map1", extent=[-80, -20, -60, 0], position=[300, 10], size=[60, 60], layers=["countries"]
    )
    mock_conn.send_command.assert_called_once_with(
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
    await mod.add_inset_map(mock_ctx, layout_name="Map1", extent=[-80, -20, -60, 0])
    mock_conn.send_command.assert_called_once_with(
        "add_inset_map", {"layout_name": "Map1", "extent": [-80, -20, -60, 0], "show_extent_indicator": True}
    )


# --- Group 4: Tools with all required params ---


async def test_get_layer_features(mock_ctx, mock_conn):
    await mod.get_layer_features(mock_ctx, layer="layer_123", limit=20)
    mock_conn.send_command.assert_called_once_with(
        "get_layer_features", {"layer": "layer_123", "limit": 20, "offset": 0}
    )


async def test_execute_processing(mock_ctx, mock_conn):
    params = {"INPUT": "layer_123", "OUTPUT": "memory:"}
    await mod.execute_processing(mock_ctx, algorithm="native:buffer", parameters=params)
    mock_conn.send_command.assert_called_once_with(
        "execute_processing", {"algorithm": "native:buffer", "parameters": params}
    )


async def test_render_map(mock_ctx, mock_conn):
    await mod.render_map(mock_ctx, path="/tmp/map.png", width=1024, height=768)
    mock_conn.send_command.assert_called_once_with("render_map", {"path": "/tmp/map.png", "width": 1024, "height": 768})


async def test_get_unique_values(mock_ctx, mock_conn):
    await mod.get_unique_values(mock_ctx, layer_name="rivers", field_name="name", limit=25)
    mock_conn.send_command.assert_called_once_with(
        "get_unique_values", {"layer_name": "rivers", "field_name": "name", "limit": 25, "offset": 0}
    )


async def test_filter_layer(mock_ctx, mock_conn):
    await mod.filter_layer(mock_ctx, layer_name="rivers", expression='"order" > 3', output_name="big_rivers")
    mock_conn.send_command.assert_called_once_with(
        "filter_layer", {"layer_name": "rivers", "expression": '"order" > 3', "output_name": "big_rivers"}
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
    mock_conn.send_command.assert_called_once_with(
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
    await mod.set_layer_visibility(mock_ctx, layer_name="rivers", visible=False)
    mock_conn.send_command.assert_called_once_with("set_layer_visibility", {"layer_name": "rivers", "visible": False})


async def test_set_canvas_extent(mock_ctx, mock_conn):
    await mod.set_canvas_extent(mock_ctx, xmin=-72, ymin=-14, xmax=-70, ymax=-13)
    mock_conn.send_command.assert_called_once_with(
        "set_canvas_extent", {"xmin": -72, "ymin": -14, "xmax": -70, "ymax": -13}
    )


async def test_style_line_graduated(mock_ctx, mock_conn):
    await mod.style_line_graduated(mock_ctx, layer_name="rivers", width_field="ORD_STRA")
    mock_conn.send_command.assert_called_once_with(
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
    await mod.style_simple(mock_ctx, layer_name="rivers", color="#0000ff", opacity=0.8)
    mock_conn.send_command.assert_called_once_with(
        "style_simple",
        {"layer_name": "rivers", "color": "#0000ff", "outline_color": "#000000", "width": 0.5, "opacity": 0.8},
    )


async def test_style_categorized(mock_ctx, mock_conn):
    await mod.style_categorized(mock_ctx, layer_name="rivers", field_name="type")
    mock_conn.send_command.assert_called_once_with(
        "style_categorized", {"layer_name": "rivers", "field_name": "type", "color_ramp": "Spectral", "width": 1.0}
    )


async def test_add_labels(mock_ctx, mock_conn):
    await mod.add_labels(mock_ctx, layer_name="rivers", field_name="name")
    mock_conn.send_command.assert_called_once_with(
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
    mock_conn.send_command.assert_called_once_with(
        "export_layout", {"layout_name": "Map1", "output_path": "/tmp/map.pdf", "dpi": 150}
    )


# --- JSON serialization ---


async def test_tool_returns_the_result_payload_as_compact_json(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "success", "result": {"key": "value"}}
    result = await mod.load_project(mock_ctx, path="/tmp/a.qgz")
    assert isinstance(result, str)
    assert result == '{"key":"value"}'
    assert json.loads(result)["key"] == "value"


async def test_a_typed_tool_returns_the_result_payload_itself(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "success", "result": {"key": "value"}}
    assert await mod.ping(mock_ctx) == {"key": "value"}


async def test_error_status_raises_tool_error(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "error", "message": "Layer 'x' not found."}
    with pytest.raises(ToolError, match="Layer 'x' not found."):
        await mod.list_layers(mock_ctx)


async def test_error_status_without_message_still_raises(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {"status": "error"}
    with pytest.raises(ToolError, match="list_layers"):
        await mod.list_layers(mock_ctx)


async def test_none_params_are_dropped_before_sending(mock_ctx, mock_conn):
    await mod.add_vector_layer(mock_ctx, path="/tmp/a.shp")
    mock_conn.send_command.assert_called_once_with("add_vector_layer", {"path": "/tmp/a.shp", "provider": "ogr"})


async def test_empty_string_path_is_sent_not_dropped(mock_ctx, mock_conn):
    await mod.save_project(mock_ctx, path="")
    mock_conn.send_command.assert_called_once_with("save_project", {"path": ""})


async def test_execute_code_raises_when_the_code_failed(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {
        "status": "success",
        "result": {"executed": False, "error": "boom", "traceback": "Traceback: boom"},
    }
    with pytest.raises(ToolError, match="Traceback: boom"):
        await mod.execute_code(mock_ctx, code="raise RuntimeError('boom')")


async def test_execute_code_returns_output_on_success(mock_ctx, mock_conn):
    mock_conn.send_command.return_value = {
        "status": "success",
        "result": {"executed": True, "stdout": "hi", "stderr": ""},
    }
    assert json.loads(await mod.execute_code(mock_ctx, code="print('hi')"))["stdout"] == "hi"


class TestStaleTokenRecovery:
    async def test_rejected_token_triggers_one_reconnect_and_retry(self, mock_ctx):
        stale = {"status": "error", "code": "unauthenticated", "message": "Authentication failed."}
        fresh = {"status": "success", "result": {"pong": True}}
        first, second = MagicMock(), MagicMock()
        first.send_command.return_value = stale
        second.send_command.return_value = fresh

        with patch.object(mod, "get_qgis_connection", side_effect=[first, second]) as mock_get:
            result = await mod.ping(mock_ctx)

        assert result == {"pong": True}
        assert mock_get.call_count == 2
        first.send_command.assert_called_once_with("ping", {})
        second.send_command.assert_called_once_with("ping", {})

    async def test_a_second_rejection_raises(self, mock_ctx):
        stale = {"status": "error", "code": "unauthenticated", "message": "Authentication failed."}
        conn = MagicMock()
        conn.send_command.return_value = stale

        with (
            patch.object(mod, "get_qgis_connection", return_value=conn),
            pytest.raises(ToolError, match="Authentication failed."),
        ):
            await mod.ping(mock_ctx)

        assert conn.send_command.call_count == 2
