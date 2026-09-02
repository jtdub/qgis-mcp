# v0.2 Release Notes

This document lists every change in the 0.2 series.

<!-- towncrier release notes start -->
## [v0.2.0 (2026-09-02)](https://github.com/jtdub/qgis-mcp/releases/tag/v0.2.0)


### Security
The QGIS MCP server now needs a token. The plugin generates one each time you start the server, and the MCP server finds it by itself. Set `QGIS_MCP_TOKEN` if it cannot.
`execute_code` is disabled. Tick "Allow execute_code" in the QGIS MCP dock to run PyQGIS code.
The plugin now listens on `127.0.0.1` only.

### Added
`get_unique_values`, `sample_features`, and `get_layer_features` take an `offset`, so you can read a large result one page at a time. Each result says whether more follows.
`create_print_layout` takes `replace`. Without it, the tool refuses to overwrite a layout that already has that name.

### Changed
`get_qgis_info` now reports the plugin version and the server version, so you can see which side is out of date.
Poetry replaces uv for development. Install with `poetry install --with dev`, and run a command with `poetry run`. You still start the server with uv, and nothing changes in your client configuration.
The repository is now `jtdub/qgis-mcp`, with a hyphen. GitHub redirects the old name, so an existing clone still works.
Run the server with the new `qgis-mcp` command. Update your client configuration; the old file path still works.
Copy the new plugin folder into your QGIS profile when you update the `qgis-mcp` package. The two now check that they speak the same protocol, and report a clear error when they do not.
Every layer tool takes a layer name, and also accepts a layer id. The `get_layers` tool is gone; use `list_layers`.
`get_layer_features` returns at most 1000 features, and shortens long geometry text.

### Fixed
The plugin failed to start, because a logging class was never imported. Start Server now works.
A failing QGIS operation now reports an error to the client, instead of a result that looks successful.
`filter_layer` and `trace_downstream` now report an error instead of returning an empty layer.
`get_unique_values` returned an arbitrary subset of the values in a field. It now returns the true set, sorted.
`render_map` drew every layer in the project. It now draws the layers on the canvas, so the image matches the screen.
`remove_layer` reported an error after it removed the layer. It now returns the id and the name of what it removed.
A dropped connection could apply a write twice. A retry now reuses the request id, and QGIS answers from its cache instead of repeating the work.
