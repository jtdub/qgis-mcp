"""End to end tests through a real MCP session and a real QGIS.

The MCP client talks to the FastMCP server over in-memory streams. The server
talks to the plugin over a real socket. QGIS answers with real layers.

These tests prove that the output schemas in models.py match what the handlers
return. A key a schema does not declare is dropped from structuredContent, and
nothing else in the suite would notice.
"""

import asyncio
import contextlib
import sys

import pytest
from conftest import POLL_SECONDS, TOKEN

if sys.version_info < (3, 10):  # pragma: no cover
    pytest.skip("The MCP server needs Python 3.10 or newer.", allow_module_level=True)

pytest.importorskip("mcp", reason="These tests need the mcp package.")
pytest.importorskip("pytest_asyncio", reason="These tests need pytest-asyncio.")

from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

import qgis_mcp.qgis_mcp_server as server_module  # noqa: E402


@pytest.fixture
def bridge(listening, monkeypatch):
    """Point the MCP server's session lookup at the running plugin."""
    monkeypatch.setenv("QGIS_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("QGIS_MCP_PORT", str(listening.port))
    monkeypatch.setenv("QGIS_MCP_TOKEN", TOKEN)
    monkeypatch.setattr(server_module, "_qgis_connection", None)

    yield listening

    server_module._reset_connection()


@contextlib.asynccontextmanager
async def pumping(plugin):
    """Poll the plugin in the background, the way its timer would."""
    running = True

    async def poll():
        while running:
            plugin.process_server()
            await asyncio.sleep(POLL_SECONDS)

    task = asyncio.ensure_future(poll())
    try:
        yield
    finally:
        running = False
        await task


@contextlib.asynccontextmanager
async def mcp_session(plugin):
    """Open an MCP client session wired to the running plugin."""
    async with pumping(plugin), create_connected_server_and_client_session(server_module.mcp) as session:
        yield session


def payload(result):
    """Return the structured content of a tool result.

    Raises:
        AssertionError: If the tool reported an error.
    """
    assert result.isError is not True, result.content
    return result.structuredContent


class TestSchemaAgreement:
    async def test_ping_matches_its_output_schema(self, bridge):
        async with mcp_session(bridge) as session:
            info = payload(await session.call_tool("ping", {}))

        assert info["pong"] is True
        assert info["protocol"] == server_module.PROTOCOL_VERSION
        assert info["execute_code_enabled"] is False

    async def test_get_qgis_info_matches_its_output_schema(self, bridge):
        async with mcp_session(bridge) as session:
            info = payload(await session.call_tool("get_qgis_info", {}))

        assert info["qgis_version"]
        assert info["profile_folder"]
        assert isinstance(info["plugins_count"], int)

    async def test_list_layers_keeps_every_vector_key(self, bridge, cities):
        async with mcp_session(bridge) as session:
            listed = payload(await session.call_tool("list_layers", {}))["result"]

        layer = listed[0]
        assert layer["name"] == "cities"
        assert layer["crs"] == "EPSG:4326"
        assert layer["geometry_type"] == "Point"
        assert layer["feature_count"] == 5
        assert [field["name"] for field in layer["fields"]] == ["name", "pop"]

    async def test_get_layer_fields_keeps_every_key(self, bridge, cities):
        async with mcp_session(bridge) as session:
            result = payload(await session.call_tool("get_layer_fields", {"layer_name": "cities"}))

        assert result["layer_name"] == "cities"
        first = result["fields"][0]
        assert set(first) == {"name", "type", "length", "precision", "comment"}

    async def test_get_unique_values_keeps_every_key(self, bridge, cities):
        async with mcp_session(bridge) as session:
            result = payload(
                await session.call_tool("get_unique_values", {"layer_name": "cities", "field_name": "name"})
            )

        assert set(result) == {
            "layer_name",
            "field_name",
            "total_count",
            "returned_count",
            "offset",
            "has_more",
            "values",
        }
        assert result["values"] == ["Arequipa", "Cusco", "Lima", "Puno"]

    async def test_sample_features_keeps_every_key(self, bridge, cities):
        async with mcp_session(bridge) as session:
            result = payload(await session.call_tool("sample_features", {"layer_name": "cities", "count": 2}))

        assert set(result) == {
            "layer_name",
            "total_count",
            "returned_count",
            "offset",
            "has_more",
            "features",
        }
        assert set(result["features"][0]) == {"id", "attributes", "geometry_wkt"}

    async def test_get_layer_extent_keeps_every_key(self, bridge, cities):
        async with mcp_session(bridge) as session:
            result = payload(await session.call_tool("get_layer_extent", {"layer_name": "cities"}))

        assert set(result) == {"layer_name", "xmin", "ymin", "xmax", "ymax"}

    async def test_get_layer_features_keeps_every_key(self, bridge, cities):
        async with mcp_session(bridge) as session:
            result = payload(await session.call_tool("get_layer_features", {"layer": "cities", "limit": 2}))

        assert result["returned_count"] == 2
        assert result["has_more"] is True

    async def test_get_project_info_keeps_every_key(self, bridge, cities):
        async with mcp_session(bridge) as session:
            result = payload(await session.call_tool("get_project_info", {}))

        assert set(result) == {"filename", "title", "layer_count", "crs", "layers"}
        assert result["layer_count"] == 1

    async def test_create_print_layout_keeps_every_key(self, bridge):
        async with mcp_session(bridge) as session:
            result = payload(await session.call_tool("create_print_layout", {"name": "Map1"}))

        assert set(result) == {"name", "page_size", "orientation", "dimensions_mm", "has_title"}
        assert set(result["dimensions_mm"]) == {"width", "height"}


class TestToolBehaviour:
    async def test_every_tool_is_listed(self, bridge):
        async with mcp_session(bridge) as session:
            listed = await session.list_tools()

        assert len(listed.tools) == 31
        assert "get_layers" not in {tool.name for tool in listed.tools}

    async def test_a_layer_id_works_where_a_name_works(self, bridge, cities):
        async with mcp_session(bridge) as session:
            by_name = payload(await session.call_tool("get_layer_features", {"layer": "cities"}))
            by_id = payload(await session.call_tool("get_layer_features", {"layer": cities.id()}))

        assert by_name["returned_count"] == by_id["returned_count"]

    async def test_a_missing_layer_reports_an_error_that_names_the_layers(self, bridge, cities):
        async with mcp_session(bridge) as session:
            result = await session.call_tool("get_layer_fields", {"layer_name": "absent"})

        assert result.isError is True
        assert "Available layers" in result.content[0].text

    async def test_execute_code_is_refused_while_the_dock_forbids_it(self, bridge):
        async with mcp_session(bridge) as session:
            result = await session.call_tool("execute_code", {"code": "pass"})

        assert result.isError is True
        assert "execute_code is disabled" in result.content[0].text

    async def test_a_write_tool_changes_the_project(self, bridge, cities):
        from qgis.core import QgsProject

        async with mcp_session(bridge) as session:
            payload(
                await session.call_tool(
                    "filter_layer",
                    {"layer_name": "cities", "expression": '"pop" > 500000', "output_name": "big"},
                )
            )

        assert QgsProject.instance().mapLayersByName("big")[0].featureCount() == 2

    async def test_a_page_can_be_walked_to_the_end(self, bridge, cities):
        collected = []
        async with mcp_session(bridge) as session:
            offset = 0
            while True:
                page = payload(
                    await session.call_tool(
                        "get_unique_values",
                        {"layer_name": "cities", "field_name": "name", "limit": 2, "offset": offset},
                    )
                )
                collected.extend(page["values"])
                if not page["has_more"]:
                    break
                offset += len(page["values"])

        assert collected == ["Arequipa", "Cusco", "Lima", "Puno"]


class TestProtocolGuard:
    async def test_a_plugin_that_speaks_another_protocol_is_refused(self, bridge, monkeypatch):
        monkeypatch.setattr(server_module, "PROTOCOL_VERSION", 99)
        server_module._reset_connection()

        async with mcp_session(bridge) as session:
            result = await session.call_tool("ping", {})

        assert result.isError is True
        assert "protocol" in result.content[0].text.lower()
