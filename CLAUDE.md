# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
uv sync                    # install dependencies
uv sync --extra dev        # install with dev/test dependencies
uv run pytest              # run all tests
uv run pytest tests/test_mcp_tools.py::test_ping  # run single test
uv run pytest --cov=src/qgis_mcp --cov-report=term-missing  # coverage
uv run ruff check .        # lint (includes isort import sorting via I rule)
uv run ruff check --fix .  # auto-fix lint issues (import sorting, etc.)
uv run ruff format --check .  # format check
uv run ruff format .       # auto-format
uv run pylint src/qgis_mcp/   # static analysis (MCP server only)
uv run mypy src/qgis_mcp/     # type check (MCP server only)
```

### Linting pipeline order
1. `ruff check --fix .` — lint + auto-fix (import sorting via isort, pyupgrade, etc.)
2. `ruff format .` — auto-format
3. `pylint src/qgis_mcp/` — static analysis
4. `mypy src/qgis_mcp/` — type checking

## Architecture

Two-process bridge between Claude and QGIS Desktop via MCP:

```
Claude / Claude Code → MCP Server (FastMCP, stdio) ↔ TCP socket (localhost:9876) ↔ QGIS Plugin (inside QGIS)
```

### MCP Server (`src/qgis_mcp/qgis_mcp_server.py`)

Runs as a separate Python process managed by `uv`. Contains:

- **`QgisMCPServer`** class — TCP socket client. Newline-framed JSON, a request id on every command, reconnection, and timeout
- **`get_qgis_connection()`** — module-level singleton managing a persistent connection
- **31 async `@mcp.tool()` functions** — each awaits `_run()`, which sends the command from a worker thread. Read tools return a `TypedDict` from `models.py`, so FastMCP publishes an output schema

### QGIS Plugin (`qgis_mcp_plugin/qgis_mcp_plugin.py`)

Runs inside QGIS's Python runtime. Contains:

- **`QgisMCPServer`** (different class, same name) — TCP socket server using `QTimer` polling (20ms), with a 16-entry response cache keyed by request id
- **`execute_command()`** with `handlers` dict mapping command strings to handler methods
- **30+ handler methods** calling PyQGIS APIs, organized by phase (introspection, filtering, styling, cartography)
- **Helpers:** `_resolve_layer()`, `_find_layer_by_name()`, `_feature_page()`, `_copy_features_to()`, `_transform_to_wgs84()`, `_geometry_type_name()`, `_get_page_dimensions()`
- **UI:** `QgisMCPDockWidget`, `QgisMCPPlugin`

### Protocol

Newline-delimited JSON over TCP. One object per line.

Request: `{"id": "<uuid hex>", "protocol": 1, "type": "command_name", "params": {...}, "token": "..."}`.

Response: `{"id": "<same id>", "protocol": 1, "status": "success", "result": {...}}` or
`{"id": ..., "protocol": 1, "status": "error", "message": "...", "code": "unauthenticated|protocol_mismatch"}`.

`PROTOCOL_VERSION` lives in both files and must match. Bump it in both when the wire format changes.
A repeated `id` is answered from the plugin's cache, so a retry never applies a write twice.

## Adding a New Tool

Every new tool requires changes in **BOTH** files:

1. **Plugin:** add handler method + register in `handlers` dict inside `execute_command()`
2. **MCP server:** add an `async @mcp.tool()` function that awaits `_run("my_tool", {params})`, or `_run_json` when the result has no fixed shape
3. If the result has a fixed shape, add a `TypedDict` to `src/qgis_mcp/models.py` and annotate the return with it
4. Update `tools.md` with parameters and return values, and the tool count in `tests/test_tool_annotations.py`

## Design Conventions

- All coordinate I/O uses **WGS84 (EPSG:4326)**. Plugin helpers handle reprojection internally.
- New tools take a **layer name**. `_resolve_layer()` also accepts a layer id, and raises with every name and id on failure.
- Memory layers from filtering/tracing are always WGS84.
- Plugin handlers accept `**kwargs` to tolerate extra JSON parameters.
- A tool must never block the event loop. Every QGIS call goes through `_run()`, which uses `anyio.to_thread`.
- A list-shaped result carries `offset`, `returned_count`, `total_count`, and `has_more`.
- The plugin file cannot be imported outside QGIS. Only `_get_page_dimensions()` is pure Python.

## Testing

Two suites. Run them in **separate** pytest processes.

```bash
uv run pytest                              # unit suite, no QGIS
./scripts/run-integration-tests.sh         # QGIS suite, local QGIS Python
./scripts/run-integration-tests.sh docker  # QGIS suite, every layer
```

WARNING: `tests/test_plugin_helpers.py` writes fake `qgis.*` entries into
`sys.modules` when it is imported. Never collect `tests/` and `tests/integration/`
in one pytest process. The unit suite's `testpaths` and the integration
`pytest.ini` keep them apart.

### Integration suite (`tests/integration/`)

Runs inside a headless QGIS. `conftest.py` collects nothing when `qgis.core`
cannot be imported, so the directory is safe to leave in place.

- `test_handlers.py` — calls each plugin handler directly, against real layers
- `test_wire.py` — drives a real socket, with the `QTimer` stopped and the poll
  pumped by hand
- `test_end_to_end.py` — a real MCP client session over in-memory streams, then
  a real socket, then real QGIS. It proves the `models.py` output schemas match
  the handler results. Needs Python 3.10 or newer, so it skips under a macOS
  QGIS bundle and runs under docker.

Build test data with `build_layer()` from `conftest.py`. A memory layer answers
`uniqueValues`, `minimumValue`, `maximumValue`, expressions, and `setFilterRect`,
so almost no test needs a file on disk.

### Unit suite (`tests/`)

Covers the MCP server side only (no QGIS needed):

- Socket client tests mock `socket.socket`
- Tool function tests mock `get_qgis_connection()` and verify `send_command()` calls
- The `_qgis_connection` module global must be reset between tests (autouse fixture)
- `tests/test_plugin_helpers.py` imports the plugin with fake `qgis.*` modules, so plugin
  dispatch, authentication, and the `execute_code` gate are tested without QGIS
- Handlers that call PyQGIS still need a running QGIS instance and are not in the suite
