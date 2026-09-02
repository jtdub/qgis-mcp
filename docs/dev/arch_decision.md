# Architecture decisions

This page records the decisions that shape the code, and why. Read it before
you argue with a convention.

## Two processes, not one

PyQGIS only exists inside QGIS. An MCP server that imported it would have to run
inside QGIS, which would tie the server's Python to the one QGIS ships, and
would make it untestable without a QGIS install.

Splitting the two lets the MCP server run on any Python 3.10 or newer, and lets
the whole tool layer be tested with no QGIS at all.

The cost is a wire protocol, and two versions that must agree.

## A socket, not a file or a pipe

The plugin runs inside a long-lived GUI process that the server does not start.
A socket is the simplest channel between two processes with independent
lifetimes, and it lets either side restart without the other.

It binds `127.0.0.1` and requires a token, so nothing off the machine can reach
it.

## Newline-delimited JSON

The first version read until `json.loads` succeeded. That re-parsed the whole
buffer after every read, and it could not tell where one message ended, so a
second request arriving in the same chunk was lost.

One JSON object per line fixes both. It costs nothing and it is easy to debug
by eye.

## A request id, and a response cache

A retry after a dropped connection could apply a write twice. Every request now
carries a uuid, and the plugin caches the last 16 answers. A retry with the same
id gets the cached answer instead of running the handler again.

The cache sits behind the token check and the protocol check, so a rejected
request is never cached and never served.

## Every coordinate is WGS84

A tool that took coordinates in the layer CRS would need the caller to know that
CRS, and to convert. An assistant gets that wrong.

One rule removes the whole class of error. The plugin reprojects at the edge.

## Read tools return a model; write tools return JSON

A read tool returns a `TypedDict`, so FastMCP publishes an output schema and the
client receives structured content. A write tool returns compact JSON, because
its result is a short confirmation with no fixed shape worth publishing.

## Async tools, always

FastMCP runs a synchronous tool on the event loop. A socket read that blocks for
up to 120 seconds would stall the whole server, including every other tool.

Every tool is `async` and goes through `anyio.to_thread`.

## The version lives in three places

`pyproject.toml` owns it. `qgis_mcp_plugin/metadata.txt` and `PLUGIN_VERSION`
must match, because the plugin ships as a zip that QGIS reads separately.

A test asserts the three agree, and the release workflow writes all three.

`PROTOCOL_VERSION` is separate. It changes only when the wire format changes.

## The plugin targets an older Python

QGIS ships its own Python, and a macOS QGIS 3.34 bundle ships 3.9. The plugin
must run there, so it uses no syntax newer than 3.9. Ruff enforces this with a
per-file ignore.

The MCP server has no such limit, and targets 3.10.

## The two test suites cannot share a process

`tests/test_plugin_helpers.py` writes fake `qgis.*` modules into `sys.modules`
so it can import the plugin without QGIS. That is global and permanent for the
process, so a real QGIS test collected afterwards would get the fakes.

Separate directories, separate pytest configurations, separate invocations.
