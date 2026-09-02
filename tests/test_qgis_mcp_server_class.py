"""Tests for QgisMCPServer socket client class."""

import json
from unittest.mock import MagicMock, patch

import pytest

from qgis_mcp.qgis_mcp_server import PROTOCOL_VERSION, QgisMCPServer, resolve_session


def _line(payload):
    """Return one framed response line."""
    return json.dumps(payload).encode("utf-8") + b"\n"


def _sent_commands(sock):
    """Return every command the client wrote to a mock socket."""
    return [json.loads(call[0][0].decode("utf-8")) for call in sock.sendall.call_args_list]


class TestInit:
    def test_defaults(self):
        server = QgisMCPServer()
        assert server.host == "127.0.0.1"
        assert server.port == 9876
        assert server.socket is None

    def test_custom_host_port(self):
        server = QgisMCPServer(host="192.168.1.1", port=1234)
        assert server.host == "192.168.1.1"
        assert server.port == 1234


class TestConnect:
    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_connect_success(self, mock_socket_class):
        server = QgisMCPServer()
        result = server.connect()
        assert result is True
        assert server.socket is not None
        mock_socket_class.return_value.connect.assert_called_once_with(("127.0.0.1", 9876))
        mock_socket_class.return_value.settimeout.assert_called_once_with(120)

    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_connect_failure(self, mock_socket_class):
        mock_socket_class.return_value.connect.side_effect = ConnectionRefusedError()
        server = QgisMCPServer()
        result = server.connect()
        assert result is False
        assert server.socket is None

    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_connect_clears_a_stale_read_buffer(self, mock_socket_class):
        server = QgisMCPServer()
        server._buffer = b"left over"
        server.connect()
        assert server._buffer == b""


class TestDisconnect:
    def test_disconnect_with_socket(self, mock_qgis_server):
        mock_sock = mock_qgis_server.socket
        mock_qgis_server.disconnect()
        mock_sock.close.assert_called_once()
        assert mock_qgis_server.socket is None

    def test_disconnect_no_socket(self):
        server = QgisMCPServer()
        server.disconnect()  # should not raise
        assert server.socket is None


class TestIsOpen:
    def test_open_when_a_socket_is_held(self, mock_qgis_server):
        assert mock_qgis_server.is_open() is True

    def test_closed_when_no_socket(self):
        assert QgisMCPServer().is_open() is False


class TestReconnect:
    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_reconnect_success(self, mock_socket_class, mock_qgis_server):
        result = mock_qgis_server._reconnect()
        assert result is True
        assert mock_qgis_server.socket is not None

    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_reconnect_failure(self, mock_socket_class, mock_qgis_server):
        mock_socket_class.return_value.connect.side_effect = ConnectionRefusedError()
        result = mock_qgis_server._reconnect()
        assert result is False


class TestSendCommand:
    def test_success(self, mock_qgis_server, make_recv_response):
        response = {"status": "success", "result": {"pong": True}}
        make_recv_response(mock_qgis_server.socket, response)

        result = mock_qgis_server.send_command("ping")

        assert result == response
        sent = _sent_commands(mock_qgis_server.socket)[0]
        assert sent["type"] == "ping"
        assert sent["params"] == {}
        assert sent["token"] == ""
        assert sent["protocol"] == PROTOCOL_VERSION
        assert isinstance(sent["id"], str) and sent["id"]

    def test_the_command_is_newline_terminated(self, mock_qgis_server, make_recv_response):
        make_recv_response(mock_qgis_server.socket, {"status": "success", "result": {}})
        mock_qgis_server.send_command("ping")
        assert mock_qgis_server.socket.sendall.call_args[0][0].endswith(b"\n")

    def test_with_params(self, mock_qgis_server, make_recv_response):
        make_recv_response(mock_qgis_server.socket, {"status": "success", "result": {}})

        mock_qgis_server.send_command("load_project", {"path": "/tmp/test.qgz"})

        assert _sent_commands(mock_qgis_server.socket)[0]["params"] == {"path": "/tmp/test.qgz"}

    def test_custom_timeout(self, mock_qgis_server, make_recv_response):
        make_recv_response(mock_qgis_server.socket, {"status": "success", "result": {}})

        mock_qgis_server.send_command("trace_downstream", timeout=300)

        mock_qgis_server.socket.settimeout.assert_any_call(300)
        mock_qgis_server.socket.settimeout.assert_called_with(QgisMCPServer.DEFAULT_TIMEOUT)

    def test_timeout_raises(self, mock_qgis_server):
        mock_qgis_server.socket.recv.side_effect = TimeoutError()

        with pytest.raises(Exception, match="Timeout"):
            mock_qgis_server.send_command("ping")

    def test_connection_closed_raises(self, mock_qgis_server):
        mock_qgis_server.socket.recv.return_value = b""

        with pytest.raises(Exception, match="Connection closed"):
            mock_qgis_server.send_command("ping")

    def test_malformed_response_raises(self, mock_qgis_server):
        mock_qgis_server.socket.recv.return_value = b"not json\n"

        with pytest.raises(Exception, match="malformed response"):
            mock_qgis_server.send_command("ping")

    def test_chunked_response(self, mock_qgis_server):
        response = {"status": "success", "result": {"data": "x" * 1000}}
        full_bytes = _line(response)

        mock_qgis_server.socket.recv.side_effect = [full_bytes[:50], full_bytes[50:]]

        assert mock_qgis_server.send_command("ping") == response

    def test_two_responses_in_one_chunk_are_read_one_at_a_time(self, mock_qgis_server):
        first = {"status": "success", "result": {"n": 1}}
        second = {"status": "success", "result": {"n": 2}}
        mock_qgis_server.socket.recv.side_effect = [_line(first) + _line(second)]

        assert mock_qgis_server.send_command("ping") == first
        assert mock_qgis_server.send_command("ping") == second

    def test_a_stale_response_is_skipped(self, mock_qgis_server):
        stale = {"id": "an-old-request", "status": "success", "result": {"stale": True}}
        wanted = {"status": "success", "result": {"fresh": True}}
        mock_qgis_server.socket.recv.side_effect = [_line(stale) + _line(wanted)]

        assert mock_qgis_server.send_command("ping") == wanted

    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_reconnects_when_disconnected(self, mock_socket_class):
        server = QgisMCPServer()
        response = {"status": "success", "result": {}}
        mock_socket_class.return_value.recv.return_value = _line(response)

        assert server.send_command("ping") == response

    def test_raises_when_reconnect_fails(self):
        server = QgisMCPServer()
        with patch("qgis_mcp.qgis_mcp_server.socket.socket") as mock_cls:
            mock_cls.return_value.connect.side_effect = ConnectionRefusedError()
            with pytest.raises(Exception, match="Could not connect"):
                server.send_command("ping")

    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_connection_error_retries(self, mock_socket_class, mock_qgis_server):
        response = {"status": "success", "result": {}}
        mock_qgis_server.socket.sendall.side_effect = BrokenPipeError()

        new_sock = MagicMock()
        new_sock.recv.return_value = _line(response)
        mock_socket_class.return_value = new_sock

        assert mock_qgis_server.send_command("ping") == response

    @patch("qgis_mcp.qgis_mcp_server.socket.socket")
    def test_the_retry_reuses_the_request_id(self, mock_socket_class, mock_qgis_server):
        first_socket = mock_qgis_server.socket
        first_socket.sendall.side_effect = [None, BrokenPipeError()]
        first_socket.recv.side_effect = BrokenPipeError()

        new_sock = MagicMock()
        new_sock.recv.return_value = _line({"status": "success", "result": {}})
        mock_socket_class.return_value = new_sock

        mock_qgis_server.send_command("filter_layer")

        first_id = _sent_commands(first_socket)[0]["id"]
        retry_id = _sent_commands(new_sock)[0]["id"]
        assert retry_id == first_id


class TestResolveSession:
    def test_environment_wins_over_the_session_file(self, monkeypatch, tmp_path):
        session = tmp_path / "session.json"
        session.write_text(json.dumps({"host": "10.0.0.1", "port": 1111, "token": "from-file"}))
        monkeypatch.setenv("QGIS_MCP_SESSION_FILE", str(session))
        monkeypatch.setenv("QGIS_MCP_TOKEN", "from-env")
        monkeypatch.setenv("QGIS_MCP_PORT", "2222")

        host, port, token = resolve_session()

        assert host == "10.0.0.1"
        assert port == 2222
        assert token == "from-env"

    def test_reads_the_session_file_the_plugin_wrote(self, monkeypatch, tmp_path):
        session = tmp_path / "session.json"
        session.write_text(json.dumps({"host": "127.0.0.1", "port": 9999, "token": "abc"}))
        monkeypatch.setenv("QGIS_MCP_SESSION_FILE", str(session))

        assert resolve_session() == ("127.0.0.1", 9999, "abc")

    def test_falls_back_to_defaults_with_no_session(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QGIS_MCP_SESSION_FILE", str(tmp_path / "absent.json"))

        assert resolve_session() == ("127.0.0.1", 9876, "")

    def test_ignores_a_corrupt_session_file(self, monkeypatch, tmp_path):
        session = tmp_path / "session.json"
        session.write_text("not json")
        monkeypatch.setenv("QGIS_MCP_SESSION_FILE", str(session))

        assert resolve_session() == ("127.0.0.1", 9876, "")
