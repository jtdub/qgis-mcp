# QGISMCP - QGIS Model Context Protocol Integration

QGISMCP connects [QGIS](https://qgis.org/) to [Claude AI](https://claude.ai/chat) through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro), allowing Claude to directly interact with and control QGIS. This integration enables prompt assisted project creation, layer loading, styling, cartography, spatial analysis, and more.

This project is strongly based on the [BlenderMCP](https://github.com/ahujasid/blender-mcp/tree/main) project by [Siddharth Ahuja](https://x.com/sidahuj)

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
- uv package manager:

If you're on Mac, please install uv as

```bash
brew install uv
```

On Windows Powershell

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Otherwise installation instructions are on their website: [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

### Download code

Download this repo to your computer. You can clone it with:

```bash
git clone git@github.com:jtdub/qgis_mcp.git
```

### QGIS plugin

You need to copy the folder [qgis_mcp_plugin](/qgis_mcp_plugin/) and its content on your QGIS profile plugins folder.

You can get your profile folder in QGIS going to menu `Settings` -> `User profiles` -> `Open active profile folder` Then, go to `Python/plugins` and paste the folder `qgis_mcp_plugin`.

> On a Windows machine the plugins folder is usually located at: `C:\Users\USER\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`

and on macOS: `~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins`

Then close QGIS and open it again. Go to the menu option `Plugins` > `Manage and Install Plugins`, select the **`Installed`** tab, and tick the QGIS MCP checkbox.

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
                "/ABSOLUTE/PATH/TO/qgis_mcp",
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
            "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/qgis_mcp", "qgis-mcp"],
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

```bash
uv sync --extra dev    # install all dependencies including test/lint tools
```

### Testing

```bash
uv run pytest                                              # run all tests
uv run pytest tests/test_mcp_tools.py::test_ping           # run a single test
uv run pytest --cov=src/qgis_mcp --cov-report=term-missing # coverage report
```

### Linting

Run in this order:

```bash
uv run ruff check --fix .        # lint + auto-fix (includes import sorting)
uv run ruff format .             # auto-format
uv run pylint src/qgis_mcp/      # static analysis
uv run mypy src/qgis_mcp/        # type checking
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development guidelines.

## Tools

See [tools.md](tools.md) for the full reference with parameters and return values.

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
