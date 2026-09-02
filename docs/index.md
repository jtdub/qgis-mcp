# QGIS MCP

QGIS MCP connects [QGIS](https://qgis.org/) to an AI assistant through the
[Model Context Protocol](https://modelcontextprotocol.io/). The assistant reads
your layers, filters them, styles them, builds a print layout, and exports a map.

## How it fits together

QGIS MCP is two processes. They talk over a TCP socket on `127.0.0.1`.

```
Your MCP client  →  MCP server (qgis-mcp)  ↔  socket 9876  ↔  QGIS plugin  →  QGIS
```

- The **MCP server** is a Python package. Your client starts it.
- The **QGIS plugin** runs inside QGIS Desktop. You start its socket server from
  a dock widget.

The two check that they speak the same protocol. Install both from the same
release.

## Where to start

| You are | Read |
| --- | --- |
| Using the tools through an assistant | [User guide](user/app_overview.md) |
| Installing or configuring the server | [Administrator guide](admin/install.md) |
| Adding a tool, or changing one | [Developer guide](dev/contributing.md) |

## Safety

Two defaults protect the QGIS session:

- The plugin listens on `127.0.0.1` only, and every request carries a token.
- `execute_code` runs arbitrary Python inside QGIS. It stays off until you tick
  a box in the dock.

Read [Configure](admin/configure.md) for both.
