"""Tests for plugin helper functions that don't require a live QGIS instance.

Uses sys.modules mocking to import the plugin module without QGIS.
The key trick is making QObject a real class so that inheritance
and super().__init__() work normally, while everything else returns MagicMock.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest


class _MockModule(types.ModuleType):
    """A module whose missing attributes resolve to MagicMock."""

    def __init__(self, name, attrs=None):
        super().__init__(name)
        for k, v in (attrs or {}).items():
            setattr(self, k, v)

    def __getattr__(self, name):
        # Avoid recursing on dunder attributes
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, mock)
        return mock


class _FakeQObject:
    """Real base class standing in for QObject."""

    pass


def _install_qgis_mocks():
    """Populate sys.modules with fake qgis packages."""
    mods = {
        "qgis": _MockModule("qgis"),
        "qgis.core": _MockModule("qgis.core"),
        "qgis.gui": _MockModule(
            "qgis.gui",
            {
                "__all__": ["QgsMessageLog"],
            },
        ),
        "qgis.utils": _MockModule("qgis.utils"),
        "qgis.PyQt": _MockModule("qgis.PyQt"),
        "qgis.PyQt.QtCore": _MockModule(
            "qgis.PyQt.QtCore",
            {
                "QObject": _FakeQObject,
                "pyqtSignal": MagicMock(return_value=MagicMock()),
            },
        ),
        "qgis.PyQt.QtWidgets": _MockModule("qgis.PyQt.QtWidgets"),
        "qgis.PyQt.QtGui": _MockModule("qgis.PyQt.QtGui"),
    }
    # Wire sub-module attributes
    mods["qgis"].core = mods["qgis.core"]
    mods["qgis"].gui = mods["qgis.gui"]
    mods["qgis"].utils = mods["qgis.utils"]
    mods["qgis"].PyQt = mods["qgis.PyQt"]
    mods["qgis.PyQt"].QtCore = mods["qgis.PyQt.QtCore"]
    mods["qgis.PyQt"].QtWidgets = mods["qgis.PyQt.QtWidgets"]
    mods["qgis.PyQt"].QtGui = mods["qgis.PyQt.QtGui"]

    sys.modules.update(mods)


_install_qgis_mocks()

# Now import the plugin — QObject is a real class, everything else is MagicMock
from qgis_mcp_plugin.qgis_mcp_plugin import PROTOCOL_VERSION
from qgis_mcp_plugin.qgis_mcp_plugin import QgisMCPServer as PluginServer


def _command(cmd_type, params=None, token="test-token", request_id="req-1", protocol=PROTOCOL_VERSION):
    """Build one well formed request for the plugin."""
    return {
        "id": request_id,
        "protocol": protocol,
        "type": cmd_type,
        "params": params or {},
        "token": token,
    }


@pytest.fixture
def plugin_server():
    """Create a PluginServer instance with mocked iface and a known token."""
    return PluginServer(iface=MagicMock(), token="test-token")


class TestGetPageDimensions:
    def test_a3_landscape(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("A3", "landscape")
        assert w == 420
        assert h == 297

    def test_a3_portrait(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("A3", "portrait")
        assert w == 297
        assert h == 420

    def test_a4_landscape(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("A4", "landscape")
        assert w == 297
        assert h == 210

    def test_a4_portrait(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("A4", "portrait")
        assert w == 210
        assert h == 297

    def test_letter_landscape(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("letter", "landscape")
        assert w == 279.4
        assert h == 215.9

    def test_letter_portrait(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("letter", "portrait")
        assert w == 215.9
        assert h == 279.4

    def test_tabloid_landscape(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("tabloid", "landscape")
        assert w == 431.8
        assert h == 279.4

    def test_tabloid_portrait(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("tabloid", "portrait")
        assert w == 279.4
        assert h == 431.8

    def test_unknown_defaults_to_a3(self, plugin_server):
        w, h = plugin_server._get_page_dimensions("legal", "landscape")
        assert w == 420
        assert h == 297


class TestExecuteCommandDispatch:
    def test_known_command_dispatches(self, plugin_server):
        """Verify execute_command routes to handler and wraps in success."""
        result = plugin_server.execute_command(_command("ping"))
        assert result["status"] == "success"
        assert result["result"]["pong"] is True

    def test_unknown_command_returns_error(self, plugin_server):
        result = plugin_server.execute_command(_command("nonexistent_command"))
        assert result["status"] == "error"
        assert "Unknown command type" in result["message"]

    def test_get_layers_is_gone(self, plugin_server):
        result = plugin_server.execute_command(_command("get_layers"))
        assert result["status"] == "error"
        assert "Unknown command type" in result["message"]

    def test_the_response_echoes_the_request_id(self, plugin_server):
        result = plugin_server.execute_command(_command("ping", request_id="abc123"))
        assert result["id"] == "abc123"
        assert result["protocol"] == PROTOCOL_VERSION


class TestProtocolVersion:
    def test_ping_reports_the_protocol_and_the_plugin_version(self, plugin_server):
        info = plugin_server.execute_command(_command("ping"))["result"]
        assert info["protocol"] == PROTOCOL_VERSION
        assert info["plugin_version"]
        assert info["execute_code_enabled"] is False

    def test_a_mismatched_protocol_is_rejected(self, plugin_server):
        result = plugin_server.execute_command(_command("ping", protocol=999))
        assert result["status"] == "error"
        assert result["code"] == "protocol_mismatch"

    def test_a_missing_protocol_is_rejected(self, plugin_server):
        command = _command("ping")
        del command["protocol"]
        result = plugin_server.execute_command(command)
        assert result["code"] == "protocol_mismatch"

    def test_the_token_is_checked_before_the_protocol(self, plugin_server):
        result = plugin_server.execute_command(_command("ping", token="wrong", protocol=999))
        assert result["code"] == "unauthenticated"


class TestResponseCache:
    def test_a_repeated_request_id_is_answered_from_the_cache(self, plugin_server):
        plugin_server._dispatch = MagicMock(return_value={"status": "success", "result": {"n": 1}})

        first = plugin_server.execute_command(_command("filter_layer", request_id="same"))
        second = plugin_server.execute_command(_command("filter_layer", request_id="same"))

        assert first is second
        plugin_server._dispatch.assert_called_once()

    def test_a_new_request_id_runs_the_handler_again(self, plugin_server):
        plugin_server._dispatch = MagicMock(return_value={"status": "success", "result": {}})

        plugin_server.execute_command(_command("filter_layer", request_id="one"))
        plugin_server.execute_command(_command("filter_layer", request_id="two"))

        assert plugin_server._dispatch.call_count == 2

    def test_the_cache_does_not_grow_without_bound(self, plugin_server):
        plugin_server._dispatch = MagicMock(return_value={"status": "success", "result": {}})

        for index in range(plugin_server.RESPONSE_CACHE_SIZE + 5):
            plugin_server.execute_command(_command("ping", request_id=f"req-{index}"))

        assert len(plugin_server.answered) == plugin_server.RESPONSE_CACHE_SIZE

    def test_a_rejected_token_is_not_cached(self, plugin_server):
        plugin_server.execute_command(_command("ping", token="wrong", request_id="same"))

        assert plugin_server.answered == {}

    def test_a_fresh_token_recovers_after_a_rejection(self, plugin_server):
        rejected = plugin_server.execute_command(_command("ping", token="wrong", request_id="same"))
        accepted = plugin_server.execute_command(_command("ping", request_id="same"))

        assert rejected["code"] == "unauthenticated"
        assert accepted["status"] == "success"

    def test_a_protocol_mismatch_is_not_cached(self, plugin_server):
        plugin_server.execute_command(_command("ping", protocol=999, request_id="same"))

        assert plugin_server.answered == {}

    def test_an_unknown_command_is_not_cached(self, plugin_server):
        plugin_server.execute_command(_command("no_such_command", request_id="same"))

        assert plugin_server.answered == {}


class TestFraming:
    def test_two_requests_in_one_chunk_both_get_an_answer(self, plugin_server):
        import json

        plugin_server.client = MagicMock()
        plugin_server.client.recv.return_value = (
            json.dumps(_command("ping", request_id="one")).encode("utf-8")
            + b"\n"
            + json.dumps(_command("ping", request_id="two")).encode("utf-8")
            + b"\n"
        )

        plugin_server._process_client()

        answered = [json.loads(call[0][0].decode("utf-8")) for call in plugin_server.client.sendall.call_args_list]
        assert [item["id"] for item in answered] == ["one", "two"]

    def test_every_response_ends_with_a_newline(self, plugin_server):
        import json

        plugin_server.client = MagicMock()
        plugin_server.client.recv.return_value = json.dumps(_command("ping")).encode("utf-8") + b"\n"

        plugin_server._process_client()

        assert plugin_server.client.sendall.call_args[0][0].endswith(b"\n")

    def test_a_partial_request_is_kept_in_the_buffer(self, plugin_server):
        import json

        plugin_server.client = MagicMock()
        payload = json.dumps(_command("ping")).encode("utf-8")
        plugin_server.client.recv.return_value = payload[:20]

        plugin_server._process_client()

        plugin_server.client.sendall.assert_not_called()
        assert plugin_server.buffer == payload[:20]

    def test_a_malformed_line_gets_an_error_and_keeps_the_client(self, plugin_server):
        import json

        plugin_server.client = MagicMock()
        plugin_server.client.recv.return_value = b"not json\n"

        plugin_server._process_client()

        response = json.loads(plugin_server.client.sendall.call_args[0][0].decode("utf-8"))
        assert response["status"] == "error"
        assert "not valid JSON" in response["message"]
        assert plugin_server.client is not None


class TestAuthentication:
    def test_missing_token_is_rejected(self, plugin_server):
        command = _command("ping")
        del command["token"]
        result = plugin_server.execute_command(command)
        assert result["status"] == "error"
        assert "Authentication failed" in result["message"]

    def test_wrong_token_is_rejected(self, plugin_server):
        result = plugin_server.execute_command(_command("ping", token="wrong"))
        assert result["status"] == "error"
        assert "Authentication failed" in result["message"]

    def test_non_string_token_is_rejected(self, plugin_server):
        result = plugin_server.execute_command(_command("ping", token=1234))
        assert result["status"] == "error"
        assert "Authentication failed" in result["message"]

    def test_a_token_is_generated_when_none_is_given(self):
        server = PluginServer(iface=MagicMock())
        assert isinstance(server.token, str)
        assert len(server.token) >= 32


class TestExecuteCodeGate:
    def test_execute_code_is_disabled_by_default(self, plugin_server):
        result = plugin_server.execute_command(_command("execute_code", {"code": "pass"}))
        assert result["status"] == "error"
        assert "execute_code is disabled" in result["message"]

    def test_execute_code_runs_when_allowed(self):
        server = PluginServer(iface=MagicMock(), token="test-token", allow_execute_code=True)
        result = server.execute_command(_command("execute_code", {"code": "print('hello')"}))
        assert result["status"] == "success"
        assert result["result"]["executed"] is True
        assert "hello" in result["result"]["stdout"]

    def test_a_failure_reports_the_traceback(self):
        server = PluginServer(iface=MagicMock(), token="test-token", allow_execute_code=True)
        result = server.execute_command(_command("execute_code", {"code": "raise RuntimeError('boom')"}))
        assert result["result"]["executed"] is False
        assert "RuntimeError" in result["result"]["traceback"]

    def test_the_redirect_is_undone_after_a_failure(self):
        import sys

        server = PluginServer(iface=MagicMock(), token="test-token", allow_execute_code=True)
        original = sys.stdout
        server.execute_command(_command("execute_code", {"code": "raise RuntimeError('boom')"}))
        assert sys.stdout is original


class TestPageBounds:
    def test_the_limit_is_clamped_to_the_maximum(self, plugin_server):
        limit, offset = plugin_server._page_bounds(99999, 0)
        assert limit == plugin_server.MAX_FEATURES_PER_REQUEST
        assert offset == 0

    def test_a_negative_limit_becomes_zero(self, plugin_server):
        assert plugin_server._page_bounds(-5, 0)[0] == 0

    def test_a_negative_offset_becomes_zero(self, plugin_server):
        assert plugin_server._page_bounds(10, -5)[1] == 0

    def test_a_string_page_is_accepted(self, plugin_server):
        assert plugin_server._page_bounds("10", "3") == (10, 3)


class TestHandlerCoverage:
    def test_every_mcp_tool_has_a_plugin_handler(self, plugin_server):
        import asyncio

        from qgis_mcp.qgis_mcp_server import mcp

        tool_names = {tool.name for tool in asyncio.run(mcp.list_tools())}
        missing = []
        for name in sorted(tool_names):
            result = plugin_server.execute_command(_command(name))
            if "Unknown command type" in str(result.get("message", "")):
                missing.append(name)
        assert missing == []


class TestVersionsAgree:
    def test_both_sides_declare_the_same_protocol(self):
        from qgis_mcp.qgis_mcp_server import PROTOCOL_VERSION as SERVER_PROTOCOL

        assert PROTOCOL_VERSION == SERVER_PROTOCOL

    def test_the_plugin_metadata_matches_the_package_version(self):
        import configparser
        import pathlib
        from importlib.metadata import version

        from qgis_mcp_plugin.qgis_mcp_plugin import PLUGIN_VERSION

        metadata = configparser.ConfigParser()
        metadata.read(pathlib.Path(__file__).resolve().parents[1] / "qgis_mcp_plugin" / "metadata.txt")

        assert metadata["general"]["version"] == PLUGIN_VERSION
        assert version("qgis-mcp") == PLUGIN_VERSION
