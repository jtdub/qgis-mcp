# Development environment

## What you need

- QGIS 3.34 LTR or newer
- Python 3.10 or newer
- [Poetry](https://python-poetry.org/docs/#installation)

Poetry builds the project and manages its dependencies. `uv` is not needed to
develop; it is one way a user runs the published server.

## Install

```bash
git clone git@github.com:jtdub/qgis-mcp.git
cd qgis-mcp
poetry install --with dev
```

Add the documentation dependencies when you work on the site:

```bash
poetry install --with dev --extras docs
```

## Link the plugin into QGIS

Symlink the plugin folder, so an edit takes effect after a QGIS restart with no
copying.

On macOS:

```bash
ln -s "$(pwd)/qgis_mcp_plugin" \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_mcp
```

On Windows Powershell:

```powershell
$src = "$(pwd)\qgis_mcp_plugin"
$dst = "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\qgis_mcp"
New-Item -ItemType SymbolicLink -Path $dst -Target $src
```

Restart QGIS, then enable **QGIS MCP** under `Plugins` > `Manage and Install Plugins`.

## The two test suites

WARNING: The two suites cannot share one pytest process. `tests/test_plugin_helpers.py`
writes fake `qgis.*` entries into `sys.modules` when it is imported. Run them
separately.

```bash
poetry run pytest                            # unit suite, no QGIS
./scripts/run-integration-tests.sh           # QGIS suite, local QGIS Python
./scripts/run-integration-tests.sh docker    # QGIS suite, every layer
```

The unit suite covers the MCP server and the parts of the plugin that do not
call PyQGIS. The integration suite runs inside a headless QGIS.

The end to end layer needs Python 3.10 or newer. A macOS QGIS bundle ships
Python 3.9, so that layer skips locally and runs under docker.

## The lint pipeline

Run in this order:

```bash
poetry run ruff check --fix .     # lint and auto-fix, including import sorting
poetry run ruff format .          # format
poetry run pylint src/qgis_mcp/   # static analysis
poetry run mypy src/qgis_mcp/     # types
```

`pylint` and `mypy` cover the MCP server only. The plugin cannot be imported
outside QGIS.

## The documentation site

```bash
poetry run mkdocs serve    # live reload on http://127.0.0.1:8000
poetry run mkdocs build    # strict build, the one CI runs
```

The build is strict. A broken link or a page missing from the navigation fails it.

## Before you open a pull request

```bash
poetry run ruff check . && poetry run ruff format --check .
poetry run pylint src/qgis_mcp/ && poetry run mypy src/qgis_mcp/
poetry run pytest
./scripts/run-integration-tests.sh
poetry run mkdocs build
```

Add a fragment under `changes/`. Read [Changelog fragments](changelog_fragments.md).
