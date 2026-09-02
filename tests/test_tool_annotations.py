"""Tests that every MCP tool declares how it affects the QGIS session."""

import asyncio

import pytest

from qgis_mcp.qgis_mcp_server import mcp

READ_ONLY_TOOLS = {
    "ping",
    "get_qgis_info",
    "get_project_info",
    "list_layers",
    "get_layer_features",
    "get_layer_fields",
    "get_unique_values",
    "sample_features",
    "get_layer_extent",
}

DESTRUCTIVE_TOOLS = {
    "load_project",
    "create_new_project",
    "save_project",
    "remove_layer",
    "execute_code",
    "execute_processing",
    "render_map",
    "export_layout",
}


@pytest.fixture(scope="module")
def tools_by_name():
    return {tool.name: tool for tool in asyncio.run(mcp.list_tools())}


def test_all_thirty_one_tools_are_registered(tools_by_name):
    assert len(tools_by_name) == 31


def test_every_tool_has_annotations(tools_by_name):
    unannotated = [name for name, tool in tools_by_name.items() if tool.annotations is None]
    assert unannotated == []


def test_every_tool_has_a_title(tools_by_name):
    untitled = [name for name, tool in tools_by_name.items() if not tool.annotations.title]
    assert untitled == []


def test_read_only_tools_are_marked_read_only(tools_by_name):
    marked = {name for name, tool in tools_by_name.items() if tool.annotations.readOnlyHint}
    assert marked == READ_ONLY_TOOLS


def test_destructive_tools_are_marked_destructive(tools_by_name):
    marked = {name for name, tool in tools_by_name.items() if tool.annotations.destructiveHint}
    assert marked == DESTRUCTIVE_TOOLS


def test_no_tool_is_both_read_only_and_destructive(tools_by_name):
    assert READ_ONLY_TOOLS.isdisjoint(DESTRUCTIVE_TOOLS)


def test_execute_code_is_destructive_and_open_world(tools_by_name):
    annotations = tools_by_name["execute_code"].annotations
    assert annotations.destructiveHint is True
    assert annotations.openWorldHint is True
    assert annotations.readOnlyHint is False


STRUCTURED_TOOLS = {
    "ping",
    "get_qgis_info",
    "get_project_info",
    "list_layers",
    "get_layer_features",
    "get_layer_fields",
    "get_unique_values",
    "sample_features",
    "get_layer_extent",
    "add_vector_layer",
    "add_raster_layer",
    "create_print_layout",
}


def test_structured_tools_publish_an_output_schema(tools_by_name):
    missing = [name for name in STRUCTURED_TOOLS if tools_by_name[name].outputSchema is None]
    assert missing == []


def test_no_tool_still_takes_a_layer_id(tools_by_name):
    with_layer_id = [
        name for name, tool in tools_by_name.items() if "layer_id" in tool.inputSchema.get("properties", {})
    ]
    assert with_layer_id == []
