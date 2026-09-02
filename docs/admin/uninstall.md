# Uninstall

## The plugin

1. Stop the plugin server in the dock.
2. In QGIS, open `Plugins` > `Manage and Install Plugins`.
3. Find **QGIS MCP** on the `Installed` tab, and uninstall it.

The plugin removes its session file when the server stops. If a stale file is
left behind, delete it:

```
<QGIS profile>/qgis_mcp/session.json
```

## The MCP server

```bash
pipx uninstall qgis-mcp
```

`uvx` leaves nothing installed, so there is nothing to remove.

## The client configuration

Remove the `qgis` entry from your MCP client configuration, then restart the
client.

## What is left behind

Nothing else. QGIS MCP writes no settings outside the session file, and it
creates no database.

A layer that `filter_layer` or `trace_downstream` built lives in the project.
If you saved the project, that layer is still in it.
