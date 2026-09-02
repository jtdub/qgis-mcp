"""Tests for get_qgis_connection() module-level connection manager."""

from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import qgis_mcp.qgis_mcp_server as mod
from qgis_mcp.qgis_mcp_server import get_qgis_connection


class TestGetQgisConnection:
    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_creates_new_connection(self, mock_cls):
        mock_server = MagicMock()
        mock_server.connect.return_value = True
        mock_server.is_open.return_value = True
        mock_cls.return_value = mock_server

        conn = get_qgis_connection()

        mock_cls.assert_called_once_with(host="127.0.0.1", port=9876, token="")
        mock_server.connect.assert_called_once()
        assert conn is mock_server

    def test_returns_existing_valid_connection(self):
        mock_server = MagicMock()
        mock_server.is_open.return_value = True
        mod._qgis_connection = mock_server

        conn = get_qgis_connection()

        assert conn is mock_server

    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_replaces_dead_connection(self, mock_cls):
        old_server = MagicMock()
        old_server.is_open.return_value = False
        mod._qgis_connection = old_server

        new_server = MagicMock()
        new_server.connect.return_value = True
        new_server.is_open.return_value = True
        mock_cls.return_value = new_server

        conn = get_qgis_connection()

        old_server.disconnect.assert_called_once()
        assert conn is new_server

    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_raises_on_connect_failure(self, mock_cls):
        mock_server = MagicMock()
        mock_server.connect.return_value = False
        mock_cls.return_value = mock_server

        with pytest.raises(Exception, match="Could not connect to QGIS"):
            get_qgis_connection()

        assert mod._qgis_connection is None

    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_uses_correct_host_port(self, mock_cls):
        mock_server = MagicMock()
        mock_server.connect.return_value = True
        mock_server.is_open.return_value = True
        mock_cls.return_value = mock_server

        get_qgis_connection()

        mock_cls.assert_called_with(host="127.0.0.1", port=9876, token="")


class TestHandshake:
    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_a_matching_protocol_is_accepted(self, mock_cls):
        server = MagicMock()
        server.connect.return_value = True
        server.is_open.return_value = True
        server.send_command.return_value = {
            "status": "success",
            "result": {"protocol": mod.PROTOCOL_VERSION, "plugin_version": "0.2.0"},
        }
        mock_cls.return_value = server

        assert get_qgis_connection() is server
        server.send_command.assert_called_once_with("ping", timeout=server.HANDSHAKE_TIMEOUT)

    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_a_mismatched_protocol_raises_and_drops_the_connection(self, mock_cls):
        server = MagicMock()
        server.connect.return_value = True
        server.send_command.return_value = {"status": "success", "result": {"protocol": 99}}
        mock_cls.return_value = server

        with pytest.raises(ToolError, match="speaks protocol 99"):
            get_qgis_connection()

        server.disconnect.assert_called_once()
        assert mod._qgis_connection is None

    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_a_rejected_token_does_not_fail_the_handshake(self, mock_cls):
        server = MagicMock()
        server.connect.return_value = True
        server.send_command.return_value = {"status": "error", "code": "unauthenticated"}
        mock_cls.return_value = server

        assert get_qgis_connection() is server
        server.disconnect.assert_not_called()

    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_a_plugin_that_never_answers_names_the_upgrade(self, mock_cls):
        server = MagicMock()
        server.connect.return_value = True
        server.send_command.side_effect = Exception("Timeout waiting for response to 'ping'.")
        mock_cls.return_value = server

        with pytest.raises(ToolError, match="did not answer the opening ping"):
            get_qgis_connection()

        server.disconnect.assert_called_once()

    @patch("qgis_mcp.qgis_mcp_server.QgisMCPServer")
    def test_a_reported_protocol_mismatch_is_surfaced(self, mock_cls):
        server = MagicMock()
        server.connect.return_value = True
        server.send_command.return_value = {
            "status": "error",
            "code": "protocol_mismatch",
            "message": "This plugin speaks protocol 2 and the client sent 1.",
        }
        mock_cls.return_value = server

        with pytest.raises(ToolError, match="speaks protocol 2"):
            get_qgis_connection()
