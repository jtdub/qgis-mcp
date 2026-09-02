"""Wire tests that drive a real socket against a real QGIS.

The QTimer is stopped, and each test pumps the poll by hand. That keeps the
tests deterministic, with no threads and no sleeps.
"""

import contextlib
import json
import socket
import time
from pathlib import Path

import pytest
from conftest import POLL_SECONDS, TOKEN, layers_named

from qgis_mcp_plugin.qgis_mcp_plugin import PROTOCOL_VERSION


@pytest.fixture
def client(listening):
    """A raw socket connected to the plugin server."""
    connection = socket.create_connection(("127.0.0.1", listening.port), timeout=5)
    connection.settimeout(0.05)
    yield connection
    connection.close()


def request(cmd_type, params=None, token=TOKEN, request_id="req-1", protocol=PROTOCOL_VERSION):
    """Return one framed request line."""
    payload = {
        "id": request_id,
        "protocol": protocol,
        "type": cmd_type,
        "params": params or {},
        "token": token,
    }
    return json.dumps(payload).encode("utf-8") + b"\n"


DEADLINE_SECONDS = 5.0
"""Longest a test waits for the answers it expects."""


def pump(server, until=None, seconds=1.0):
    """Poll the server until a condition holds, or until the time runs out.

    Without a condition the poll runs for a short fixed window. That is how a
    test waits for something that must not happen.
    """
    deadline = time.monotonic() + (seconds if until else 0.1)
    while time.monotonic() < deadline:
        server.process_server()
        if until is not None and until():
            return
        time.sleep(POLL_SECONDS)


def exchange(server, connection, payload, expect=1):
    """Write a request, poll the server, and return the answers it sends.

    A socket with nothing to read raises. The name of that error differs
    between Python versions, so the whole OSError family is caught.

    Raises:
        AssertionError: If the answers do not arrive before the deadline.
    """
    connection.sendall(payload)
    deadline = time.monotonic() + DEADLINE_SECONDS
    buffer = b""
    lines = []
    while len(lines) < expect and time.monotonic() < deadline:
        server.process_server()
        with contextlib.suppress(OSError):
            buffer += connection.recv(65536)
        while b"\n" in buffer and len(lines) < expect:
            line, buffer = buffer.split(b"\n", 1)
            lines.append(json.loads(line.decode("utf-8")))
        time.sleep(POLL_SECONDS)

    assert len(lines) == expect, f"Expected {expect} answers, got {len(lines)}"
    return lines


class TestRoundTrip:
    def test_a_good_request_gets_a_success(self, listening, client):
        response = exchange(listening, client, request("ping"))[0]

        assert response["status"] == "success"
        assert response["result"]["pong"] is True

    def test_the_response_echoes_the_request_id(self, listening, client):
        assert exchange(listening, client, request("ping", request_id="abc"))[0]["id"] == "abc"

    def test_the_response_carries_the_protocol(self, listening, client):
        assert exchange(listening, client, request("ping"))[0]["protocol"] == PROTOCOL_VERSION

    def test_a_handler_result_crosses_the_socket(self, listening, client, cities):
        result = exchange(listening, client, request("list_layers"))[0]["result"]

        assert [layer["name"] for layer in result] == ["cities"]

    def test_a_handler_error_crosses_the_socket(self, listening, client):
        response = exchange(listening, client, request("get_layer_fields", {"layer_name": "absent"}))[0]

        assert response["status"] == "error"
        assert "Available layers" in response["message"]

    def test_an_unknown_command_is_reported(self, listening, client):
        response = exchange(listening, client, request("no_such_command"))[0]

        assert "Unknown command type" in response["message"]


class TestAuthentication:
    def test_a_wrong_token_is_refused(self, listening, client):
        response = exchange(listening, client, request("ping", token="wrong"))[0]

        assert response["code"] == "unauthenticated"

    def test_a_refused_request_still_carries_its_id(self, listening, client):
        response = exchange(listening, client, request("ping", token="wrong", request_id="xyz"))[0]

        assert response["id"] == "xyz"

    def test_a_refused_request_never_reaches_a_handler(self, listening, client, cities):
        exchange(listening, client, request("remove_layer", {"layer": "cities"}, token="wrong"))

        assert layers_named("cities") != []

    def test_the_session_file_publishes_the_token(self, listening):
        with open(listening.session_file_path(), encoding="utf-8") as handle:
            published = json.load(handle)

        assert published["token"] == TOKEN
        assert published["port"] == listening.port

    def test_stopping_the_server_removes_the_session_file(self, listening):
        path = Path(listening.session_file_path())
        listening.stop()

        assert not path.exists()


class TestProtocolVersion:
    def test_a_wrong_protocol_is_refused(self, listening, client):
        response = exchange(listening, client, request("ping", protocol=99))[0]

        assert response["code"] == "protocol_mismatch"
        assert "99" in response["message"]

    def test_a_missing_protocol_is_refused(self, listening, client):
        payload = json.loads(request("ping").decode("utf-8"))
        del payload["protocol"]

        response = exchange(listening, client, json.dumps(payload).encode("utf-8") + b"\n")[0]

        assert response["code"] == "protocol_mismatch"


class TestFraming:
    def test_two_requests_in_one_write_both_get_an_answer(self, listening, client):
        payload = request("ping", request_id="one") + request("ping", request_id="two")

        answers = exchange(listening, client, payload, expect=2)

        assert [item["id"] for item in answers] == ["one", "two"]

    def test_a_partial_request_gets_no_answer_yet(self, listening, client):
        payload = request("ping", request_id="split")

        client.sendall(payload[:15])
        pump(listening, until=lambda: listening.buffer == payload[:15])

        assert listening.buffer == payload[:15]

    def test_a_request_split_across_two_writes_is_answered(self, listening, client):
        payload = request("ping", request_id="split")
        client.sendall(payload[:15])
        pump(listening, until=lambda: listening.buffer == payload[:15])

        assert exchange(listening, client, payload[15:])[0]["id"] == "split"

    def test_a_malformed_line_is_reported(self, listening, client):
        response = exchange(listening, client, b"not json\n")[0]

        assert "not valid JSON" in response["message"]

    def test_the_client_survives_a_malformed_line(self, listening, client):
        exchange(listening, client, b"not json\n")

        assert exchange(listening, client, request("ping", request_id="after"))[0]["id"] == "after"

    def test_a_blank_line_is_ignored(self, listening, client):
        payload = b"\n" + request("ping", request_id="after-blank")

        assert exchange(listening, client, payload)[0]["id"] == "after-blank"


class TestRequestCache:
    def test_a_repeated_id_does_not_run_the_handler_twice(self, listening, client, cities):
        payload = request("filter_layer", {"layer_name": "cities", "expression": '"pop" > 0', "output_name": "a"})

        first = exchange(listening, client, payload)[0]
        second = exchange(listening, client, payload)[0]

        assert first == second
        assert len(layers_named("a")) == 1

    def test_a_new_id_runs_the_handler_again(self, listening, client, cities):
        params = {"layer_name": "cities", "expression": '"pop" > 0', "output_name": "b"}

        exchange(listening, client, request("filter_layer", params, request_id="one"))
        exchange(listening, client, request("filter_layer", params, request_id="two"))

        assert len(layers_named("b")) == 2

    def test_the_cache_survives_a_reconnect(self, listening, client, cities):
        payload = request("filter_layer", {"layer_name": "cities", "expression": '"pop" > 0', "output_name": "c"})
        first = exchange(listening, client, payload)[0]

        client.close()
        pump(listening, until=lambda: listening.client is None)
        again = socket.create_connection(("127.0.0.1", listening.port), timeout=5)
        again.settimeout(0.05)
        try:
            second = exchange(listening, again, payload)[0]
        finally:
            again.close()

        assert first == second
        assert len(layers_named("c")) == 1
