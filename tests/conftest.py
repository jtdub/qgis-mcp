"""Shared fixtures for QGIS MCP tests."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from qgis_mcp.qgis_mcp_server import QgisMCPServer


@pytest.fixture
def mock_socket():
    """A mock socket that simulates a connected state."""
    sock = MagicMock()
    return sock


@pytest.fixture
def mock_qgis_server(mock_socket):
    """QgisMCPServer with a pre-connected mock socket."""
    server = QgisMCPServer()
    server.socket = mock_socket
    return server


@pytest.fixture
def make_recv_response():
    """Factory to configure a mock socket's recv to return a JSON response."""

    def _make(sock, response_dict):
        sock.recv.return_value = json.dumps(response_dict).encode("utf-8") + b"\n"

    return _make


@pytest.fixture
def success_response():
    """Standard success response dict."""
    return {"status": "success", "result": {"pong": True}}


@pytest.fixture
def mock_ctx():
    """Mock MCP Context object. Its report_progress and info are awaitable."""
    return AsyncMock()


@pytest.fixture(autouse=True)
def isolate_session_lookup(monkeypatch, tmp_path):
    """Keep resolve_session away from any real QGIS profile on this machine."""
    for name in ("QGIS_MCP_HOST", "QGIS_MCP_PORT", "QGIS_MCP_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QGIS_MCP_SESSION_FILE", str(tmp_path / "absent-session.json"))


@pytest.fixture(autouse=True)
def reset_global_connection():
    """Reset the module-level _qgis_connection before each test."""
    import qgis_mcp.qgis_mcp_server as mod

    original = mod._qgis_connection
    mod._qgis_connection = None
    yield
    mod._qgis_connection = original
