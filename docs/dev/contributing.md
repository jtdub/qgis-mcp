# Contributing to QGIS MCP

Thank you for your interest in contributing!
This project connects [QGIS](https://qgis.org/) to [Claude AI](https://claude.ai/chat) through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro). Your help in improving this integration is very welcome.

## Getting Started

1. **Fork the Repository**
   Clone your fork locally:
   ```bash
   git clone git@github.com:YOUR-USERNAME/qgis-mcp.git
   cd qgis-mcp
   ```

2. **Install Prerequisites**
   - QGIS 3.34 LTR or newer
   - Python 3.10 or newer
   - [Poetry](https://python-poetry.org/docs/#installation)
   - Claude Desktop or Claude Code

   Install Poetry with the official installer:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

   On Windows Powershell:
   ```powershell
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
   ```

3. **Install Dependencies**
   ```bash
   poetry install --extras dev
   ```

4. **Set Up the QGIS Plugin**
   Create a symlink from this repo's `qgis_mcp_plugin` folder to your QGIS profile plugin directory.

   On Mac:
   ```bash
   ln -s $(pwd)/qgis_mcp_plugin ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_mcp
   ```

   On Windows Powershell:
   ```powershell
   $src = "$(pwd)\qgis_mcp_plugin"
   $dst = "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\qgis_mcp"
   New-Item -ItemType SymbolicLink -Path $dst -Target $src
   ```

   Restart QGIS, go to `Plugins` > `Manage and Install Plugins`, search for **QGIS MCP**, and enable it.

5. **Configure Claude Desktop**
   Add the server configuration to `claude_desktop_config.json`:
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

## Development Workflow

- Start the QGIS plugin (`Plugins` > `QGIS MCP` > `Start Server`).
- Run the MCP server via Claude Desktop integration.
- Make your changes and test locally.

## Testing

Run the full test suite:

```bash
poetry run pytest
```

Run a single test:

```bash
poetry run pytest tests/test_mcp_tools.py::test_ping
```

Run with coverage:

```bash
poetry run pytest --cov=src/qgis_mcp --cov-report=term-missing
```

Tests cover the MCP server side, and the parts of the plugin that do not call PyQGIS. `tests/test_plugin_helpers.py` imports the plugin with fake `qgis.*` modules, so command dispatch, authentication, and the `execute_code` gate are tested without QGIS. Handlers that call PyQGIS still need a running QGIS instance and are not part of the automated suite.

### Integration tests against a real QGIS

The unit suite never starts QGIS. The integration suite does.

```bash
./scripts/run-integration-tests.sh          # uses a local QGIS Python
./scripts/run-integration-tests.sh docker   # runs every layer in a container
```

The suite has three layers:

- `tests/integration/test_handlers.py` calls each plugin handler against real layers.
- `tests/integration/test_wire.py` drives a real socket, and pumps the poll by hand.
- `tests/integration/test_end_to_end.py` calls the tools through a real MCP client
  session. It proves the output schemas match what the handlers return.

WARNING: The two suites cannot share one pytest process. `tests/test_plugin_helpers.py`
installs fake `qgis.*` modules on import. Run `poetry run pytest` and the script separately.

The end to end layer needs Python 3.10 or newer. A macOS QGIS bundle ships Python 3.9,
so that layer skips locally and runs under docker.

If `qgis.core` cannot be imported, the integration directory collects nothing.

## Linting

Run the full linting pipeline in this order:

```bash
poetry run ruff check --fix .        # lint + auto-fix (includes import sorting)
poetry run ruff format .             # auto-format
poetry run pylint src/qgis_mcp/      # static analysis (MCP server only)
poetry run mypy src/qgis_mcp/        # type checking (MCP server only)
```

Import sorting is handled by ruff's built-in isort rule (`I` in the ruff `select` list). There is no need for a separate `isort` installation.

## Adding a New Tool

Every new tool requires changes in **both** the plugin and the MCP server:

1. **Plugin** (`qgis_mcp_plugin/qgis_mcp_plugin.py`): add a handler method and register it in the `handlers` dict inside `execute_command()`
2. **MCP server** (`src/qgis_mcp/qgis_mcp_server.py`): add an `@mcp.tool()` function that calls `qgis.send_command("my_tool", {params})`
3. **Docs**: update [the tool reference](../user/tool_reference.md) with parameters and return values

All coordinate I/O uses **WGS84 (EPSG:4326)**. Use `_resolve_layer()` for layer lookup. It accepts a layer name or a layer id.

## Contributing Guidelines

- Open an issue before you file a pull request. This avoids work on a change we cannot accept.
- Keep PRs focused on a single change.
- Write clear commit messages.
- Ensure tests pass and linters are clean before submitting.
- Update docs if behavior changes.
- Be cautious when using `execute_code` (it runs arbitrary PyQGIS).

## AI Assisted Contributions

Much of this project was written with an AI assistant. That is allowed, and it
is expected. Two rules matter most:

- **Say so in the pull request**, and say which part.
- **You own every line.** "The model wrote it" is not an answer in review.

One failure costs this project more than any other: an assistant will invent a
PyQGIS method that does not exist, and neither `mypy`, `pylint`, nor the unit
suite can catch it. Only the QGIS API documentation and the integration suite
can.

Read [AI assisted contributions](ai_assisted_contributions.md) before you open
a pull request written with one.

## Changelog Fragments

`docs/admin/release_notes/` is built, not written. Add a file under `changes/`
named `<issue>.<type>`, and `towncrier build` assembles the notes during a
release.

```bash
echo "\`filter_layer\` takes \`output_crs\`. The output used to be WGS84 always." > changes/42.changed
poetry run towncrier build --version 0.3.0 --draft   # read the result
```

An internal refactor needs no fragment. Apply the `no-changelog` label instead.

Read [Changelog fragments](changelog_fragments.md) for the rules.

## Opening a Pull Request

GitHub fills the description from
[`.github/pull_request_template.md`](https://github.com/jtdub/qgis-mcp/blob/develop/.github/pull_request_template.md).

- Name the issue the change closes on the `# Closes:` line.
- Say in the Test plan how a reviewer confirms the change works.
- Tick a checklist item only when it is done. Leave the rest unticked, and say why.

## Releasing

A release is driven by two workflows. Read
[the release checklist](release_checklist.md) before you run either.

- **Prepare Release** bumps the version, builds the notes from `changes/`, and
  opens a release pull request.
- **Release** runs when you publish the GitHub release. It builds the package
  and the plugin zip, publishes to PyPI, and moves `main`.

## Reporting Issues

Use [GitHub Issues](https://github.com/jtdub/qgis-mcp/issues). Pick the template
that fits:

- **Bug report** asks for the QGIS version, the plugin version, the `qgis-mcp`
  version, and the QGIS MCP log panel. QGIS MCP runs as two processes, so a
  fault can sit in either one.
- **Feature request** asks what you cannot do today, and what a new tool would
  return.
