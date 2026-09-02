# QGISMCP - QGIS Model Context Protocol Integration

[![PyPI](https://img.shields.io/pypi/v/qgis-mcp)](https://pypi.org/project/qgis-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/qgis-mcp)](https://pypi.org/project/qgis-mcp/)
[![CI](https://github.com/jtdub/qgis-mcp/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/jtdub/qgis-mcp/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

QGISMCP connects [QGIS](https://qgis.org/) to [Claude AI](https://claude.ai/chat) through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro), allowing Claude to directly interact with and control QGIS. This integration enables prompt assisted project creation, layer loading, styling, cartography, spatial analysis, and more.

This project is strongly based on the [BlenderMCP](https://github.com/ahujasid/blender-mcp/tree/main) project by [Siddharth Ahuja](https://x.com/sidahuj)

**[Read the documentation](https://qgis-mcp.readthedocs.io/)** for the user,
administrator, and developer guides.

## Features

- **Two-way communication**: Connect Claude AI to QGIS through a socket-based server
- **Project manipulation**: Create, load and save projects in QGIS
- **Layer introspection**: Explore layers, fields, unique values, extents, and sample features
- **Filtering & spatial ops**: Expression-based filtering, downstream river tracing, visibility and extent control
- **Styling**: Simple, graduated, and categorized renderers plus labeling with line-following support
- **Print layouts**: Create publication-quality maps with legends, inset maps, scale bars, and export to PDF/PNG
- **Processing**: Execute processing algorithms from the Processing Toolbox
- **Code execution**: Run arbitrary Python code in QGIS from Claude

All coordinate inputs accept **WGS84 (EPSG:4326)**. All coordinate outputs are returned in **WGS84**.

## Components

The system consists of two main components:

1. **[QGIS plugin](/qgis_mcp_plugin/)**: A QGIS plugin that creates a socket server within QGIS to receive and execute commands.
2. **[MCP Server](/src/qgis_mcp/qgis_mcp_server.py)**: A Python server that implements the Model Context Protocol and connects to the QGIS plugin.

## Installation

### Prerequisites

- QGIS 3.34 LTR or newer
- Claude Desktop or Claude Code
- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/), to run the server

Install uv on Mac:

```bash
brew install uv
```

On Windows Powershell:

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

uv runs the server from your clone. You do not need it to develop.
[Poetry](https://python-poetry.org/docs/#installation) builds the project and
manages its dependencies, and the Development section below uses it.

### The MCP server

Run it straight from PyPI. You do not need a clone.

```bash
uvx qgis-mcp        # run it without installing
pipx install qgis-mcp   # or install it once
```

To work from a clone instead:

```bash
git clone git@github.com:jtdub/qgis-mcp.git
```

### QGIS plugin

The plugin and the server check that they speak the same protocol, so install
the two from the same release.

Download `qgis_mcp_plugin-<version>.zip` from the
[latest release](https://github.com/jtdub/qgis-mcp/releases/latest). In QGIS,
open `Plugins` > `Manage and Install Plugins` > `Install from ZIP`, choose the
file, and install it.

To install from a clone instead, copy the folder
[qgis_mcp_plugin](/qgis_mcp_plugin/) into your QGIS profile plugins folder.
Find that folder in QGIS at `Settings` > `User profiles` >
`Open active profile folder`, then go to `python/plugins`.

> On Windows the plugins folder is usually `C:\Users\USER\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`

and on macOS: `~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins`

Then restart QGIS. Go to `Plugins` > `Manage and Install Plugins`, select the
**`Installed`** tab, and tick the QGIS MCP checkbox.

> The `All` tab lists the official QGIS Plugin Repository. This plugin is not published there yet, so you will not find it in that tab.

### Claude for Desktop Integration

Go to `Claude` > `Settings` > `Developer` > `Edit Config` > `claude_desktop_config.json` to include the following:

> If you can't find the "Developers tab" or the `claude_desktop_config.json` look at this [documentation](https://modelcontextprotocol.io/quickstart/user#2-add-the-filesystem-mcp-server).

```json
{
    "mcpServers": {
        "qgis": {
            "command": "uv",
            "args": [
                "run",
                "--directory",
                "/ABSOLUTE/PATH/TO/qgis-mcp",
                "qgis-mcp"
            ]
        }
    }
}
```

Point `--directory` at the repository root, the folder that holds `pyproject.toml`.

### Authentication

The plugin generates a token each time you start the server, and it writes that token to a
session file inside your QGIS profile. The MCP server finds the file by itself, so you
normally do nothing.

If the MCP server cannot find the file, copy the token from the dock widget and set it in
the environment:

```json
{
    "mcpServers": {
        "qgis": {
            "command": "uv",
            "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/qgis-mcp", "qgis-mcp"],
            "env": { "QGIS_MCP_TOKEN": "the-token-from-the-dock" }
        }
    }
}
```

These environment variables override the session file:

| Variable | Purpose | Default |
| --- | --- | --- |
| `QGIS_MCP_TOKEN` | The token the plugin shows in the dock | from the session file |
| `QGIS_MCP_HOST` | The host to connect to | `127.0.0.1` |
| `QGIS_MCP_PORT` | The port the plugin listens on | `9876` |
| `QGIS_MCP_SESSION_FILE` | An explicit path to the session file | the default QGIS profile |

WARNING: `execute_code` runs unrestricted Python inside QGIS. It is disabled by default.
Tick "Allow execute_code" in the dock widget only when you need it.

## Usage

### Starting the Connection

1. In QGIS, go to `plugins` > `QGIS MCP` > `QGIS MCP`
    ![plugins menu](/assets/imgs/qgis-plugins-menu.png)
2. Click "Start Server"
    ![start server](/assets/imgs/qgis-mcp-start-server.png)

### Using with Claude

Once the config file has been set on Claude, and the server is running on QGIS, you will see a hammer icon with tools for the QGIS MCP.

![Claude tools](assets/imgs/claude-available-tools.png)

## Development

### Setup

Poetry manages the dependencies and owns the version.

```bash
poetry install --extras dev    # install all dependencies including test/lint tools
```

### Testing

```bash
poetry run pytest                                              # run all tests
poetry run pytest tests/test_mcp_tools.py::test_ping           # run a single test
poetry run pytest --cov=src/qgis_mcp --cov-report=term-missing # coverage report
```

### Linting

Run in this order:

```bash
poetry run ruff check --fix .        # lint + auto-fix (includes import sorting)
poetry run ruff format .             # auto-format
poetry run pylint src/qgis_mcp/      # static analysis
poetry run mypy src/qgis_mcp/        # type checking
```

See the [developer guide](docs/dev/contributing.md) for full development guidelines.

## Tools

See the [tool reference](docs/user/tool_reference.md) for the full list with parameters and return values.

### Project Management
- `ping` — check server connectivity
- `get_qgis_info` — QGIS version and profile info
- `create_new_project` — create and save new project
- `load_project` — load QGIS project file
- `get_project_info` — project metadata and layer list
- `save_project` — save current project

### Layer Management
- `add_vector_layer` — add vector layer (shapefile, GeoJSON, GeoPackage)
- `add_raster_layer` — add raster layer (GeoTIFF, etc.)
- `remove_layer` — remove layer by ID
- `zoom_to_layer` — zoom to layer extent

### Introspection
- `list_layers` — all layers with CRS, fields, geometry type, feature count
- `get_layer_fields` — detailed field info (type, length, precision)
- `get_unique_values` — one sorted page of the distinct values a field holds
- `sample_features` — sample features with optional expression filter
- `get_layer_extent` — bounding box in WGS84

### Filtering & Spatial Operations
- `filter_layer` — expression-based filtering to memory layer
- `trace_downstream` — network topology tracing (HydroSHEDS compatible)
- `set_layer_visibility` — toggle layer visibility
- `set_canvas_extent` — set map canvas extent in WGS84

### Styling
- `style_line_graduated` — graduated line width by field value
- `style_simple` — simple single-symbol styling
- `style_categorized` — categorized styling with color ramp
- `add_labels` — labeling with line-following and buffer support

### Print Layout & Cartography
- `create_print_layout` — layout with map, title, scale bar, north arrow
- `add_legend` — filtered legend with positioning
- `add_inset_map` — inset/overview map with extent indicator
- `export_layout` — export to PDF or image

### Utilities
- `get_layer_features` — one page of vector features
- `execute_processing` — run QGIS Processing algorithms
- `render_map` — render map canvas to image
- `execute_code` — execute arbitrary PyQGIS code

## License

QGIS MCP is licensed under the [Apache License 2.0](LICENSE).

It is a derivative of [BlenderMCP](https://github.com/ahujasid/blender-mcp),
which is MIT licensed. The [NOTICE](NOTICE) file carries the MIT copyright and
permission notice, as that licence requires. Keep `NOTICE` with the work if you
redistribute it.

Read the [licensing decision](docs/dev/licensing.md) for why Apache-2.0, and how
it sits alongside the GPL that QGIS itself uses.
