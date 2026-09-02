# Compatibility matrix

## The two sides must match

The MCP server and the QGIS plugin carry a protocol version. They compare it
when the server connects, and refuse to work when it differs.

| qgis-mcp | QGIS plugin | Protocol |
| --- | --- | --- |
| 0.2.x | 0.2.x | 1 |

Install both from the same release. Read [Upgrade](upgrade.md).

## QGIS

| QGIS | Supported | Notes |
| --- | --- | --- |
| 3.34 LTR | Yes | The version CI tests against |
| 3.40 and newer | Expected to work | Not tested in CI |
| Older than 3.34 | No | `qgisMinimumVersion` is 3.34 |

The integration suite runs inside the `qgis/qgis:ltr` container, so the tested
QGIS moves when that tag moves.

## Python

Two different Pythons are involved.

**The MCP server** runs on your machine, under the Python your client starts.

| Python | Supported |
| --- | --- |
| 3.10 to 3.13 | Yes, tested in CI |
| 3.9 and older | No |

**The plugin** runs inside QGIS, under the Python QGIS ships. You do not choose
it. A macOS QGIS 3.34 bundle ships Python 3.9, and the plugin runs there. The
plugin uses no syntax newer than 3.9 for this reason.

## Operating systems

| System | Notes |
| --- | --- |
| macOS | Tested by hand |
| Linux | Tested in CI, in the QGIS container |
| Windows | Expected to work. The session file path follows `APPDATA`. |

## MCP clients

Any client that speaks the Model Context Protocol over stdio. Claude Desktop
and Claude Code are the ones used during development.

A client that reads an output schema gets structured results from the read
tools. A client that does not still gets the same data as text.
