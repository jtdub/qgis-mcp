# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
poetry install --extras dev                  # install dependencies, including dev
poetry run pytest                            # run all tests
poetry run pytest tests/test_mcp_tools.py::test_ping   # run single test
poetry run pytest --cov=src/qgis_mcp --cov-report=term-missing  # coverage
poetry run ruff check .                      # lint (includes isort import sorting via I rule)
poetry run ruff check --fix .                # auto-fix lint issues (import sorting, etc.)
poetry run ruff format --check .             # format check
poetry run ruff format .                     # auto-format
poetry run pylint src/qgis_mcp/              # static analysis (MCP server only)
poetry run mypy src/qgis_mcp/                # type check (MCP server only)
poetry version patch                         # bump the version; poetry owns it
poetry lock                                  # regenerate poetry.lock
poetry run towncrier build --version X.Y.Z --draft  # preview the release notes
```

### The container environment

`invoke` runs every check against the same QGIS CI uses. `invoke --list` shows
the tasks; `tasks.py` defines them.

```bash
invoke build          # build the image
invoke tests          # lint, types, both suites
invoke integration    # the QGIS suite only
invoke cli            # a shell in the container
```

Set `local: true` in `invoke.yml` to run a task on this machine instead.

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

Runs as a separate Python process. Poetry builds it; a user starts it with `uv run` or the `qgis-mcp` console script. Contains:

- **`QgisMCPServer`** class — TCP socket client. Newline-framed JSON, a request id on every command, reconnection, and timeout
- **`get_qgis_connection()`** — module-level singleton managing a persistent connection
- **31 async `@mcp.tool()` functions** — a read tool awaits `_run_as(Model, ...)` and returns a `TypedDict` from `models.py`, so FastMCP publishes an output schema. A write tool awaits `_run_json()` and returns compact JSON. Only a tool that reports progress takes `ctx: Context`

### QGIS Plugin (`qgis_mcp_plugin/qgis_mcp_plugin.py`)

Runs inside QGIS's Python runtime. Contains:

- **`QgisMCPServer`** (different class, same name) — TCP socket server using `QTimer` polling (20ms), with a 16-entry response cache keyed by request id
- **`execute_command()`** with `handlers` dict mapping command strings to handler methods
- **30+ handler methods** calling PyQGIS APIs, organized by phase (introspection, filtering, styling, cartography)
- **Helpers:** `_resolve_layer()`, `_require_vector()`, `_field_index()`, `_feature_page()`, `_copy_features_to()`, `_symbol_for()`, `_transform()`, `_rect_to_wgs84()`, `_find_layout()`, `_main_map_item()`
- **UI:** `QgisMCPDockWidget`, `QgisMCPPlugin`

### Protocol

Newline-delimited JSON over TCP. One object per line.

Request: `{"id": "<uuid hex>", "protocol": 1, "type": "command_name", "params": {...}, "token": "..."}`.

Response: `{"id": "<same id>", "protocol": 1, "status": "success", "result": {...}}` or
`{"id": ..., "protocol": 1, "status": "error", "message": "...", "code": "unauthenticated|protocol_mismatch"}`.

`PROTOCOL_VERSION` lives in both files and must match. Bump it in both when the wire format changes.
A repeated `id` is answered from the plugin's cache, so a retry never applies a write twice.

## Changelog

Never edit `docs/admin/release_notes/`. Add a fragment to `changes/`, named
`<issue>.<type>`, where the type is one of `security`, `added`, `changed`,
`deprecated`, `removed`, `fixed`, `dependencies`, or `documentation`.

One item on one line. At most three items. Write for the operator, not the
reviewer. `docs/dev/changelog_fragments.md` holds the rules.

## Adding a New Tool

Every new tool requires changes in **BOTH** files:

1. **Plugin:** add handler method + register in `handlers` dict inside `execute_command()`
2. **MCP server:** add an `async @mcp.tool()` function. A read tool awaits `_run_as(Model, "my_tool", {params})`; a write tool awaits `_run_json("my_tool", {params})`
3. For a read tool, add a `TypedDict` to `src/qgis_mcp/models.py` and annotate the return with it. Add `ctx: Context` only when the tool reports progress
4. **Tests:** a unit test in `tests/test_mcp_tools.py`, and an integration test in `tests/integration/test_handlers.py`. A handler with no integration test is a handler nobody has run
5. Update `docs/user/tool_reference.md` with parameters and return values, and the tool count in `tests/test_tool_annotations.py`
6. Add a fragment under `changes/`

## Verify Every PyQGIS Call

Nothing in the unit suite catches an invented PyQGIS method.

- `mypy` cannot: PyQGIS is untyped here.
- `pylint` cannot: `qgis.*` is in its ignored-modules list.
- The unit suite cannot: `tests/test_plugin_helpers.py` replaces `qgis.*` with
  mocks that answer any attribute.

Check every PyQGIS call against the [QGIS 3.34 API documentation](https://qgis.org/pyqgis/3.34/),
and cover the handler with an integration test. Those are the only two things
that catch it.

The same applies to the MCP SDK. Check `FastMCP` behaviour against the installed
package under `.venv`, not against memory.

`docs/dev/ai_assisted_contributions.md` states this for a human contributor.

## Design Conventions

- All coordinate I/O uses **WGS84 (EPSG:4326)**. Plugin helpers handle reprojection internally.
- New tools take a **layer name**. `_resolve_layer()` also accepts a layer id, and raises with every name and id on failure.
- Memory layers from filtering/tracing are always WGS84.
- Plugin handlers accept `**kwargs` to tolerate extra JSON parameters.
- A tool must never block the event loop. Every QGIS call goes through `_run()`, which uses `anyio.to_thread`.
- A list-shaped result carries `offset`, `returned_count`, `total_count`, and `has_more`.
- A handler that loops calls `_pump_ui()` freely. The helper throttles itself, so no handler picks a rate.
- Build a `QgsCoordinateTransform` once with `_transform()` and reuse it. Never build one inside a per-feature loop.
- The plugin file cannot be imported outside QGIS. Only `_get_page_dimensions()` is pure Python.

## Documentation

The site is MkDocs, in `docs/`, with the navigation in `mkdocs.yml`.

```bash
poetry install --extras docs
poetry run mkdocs serve          # live reload
poetry run mkdocs build --strict # the build CI runs
```

The build is strict. A broken link, or a page missing from the navigation,
fails it. `CONTRIBUTING.md` and `CHANGELOG.md` at the root are pointers; the
content lives under `docs/`.

## Testing

Two suites. Run them in **separate** pytest processes.

```bash
poetry run pytest                              # unit suite, no QGIS
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
