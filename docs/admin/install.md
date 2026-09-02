# Install

QGIS MCP is two pieces. Install both, from the same release.

## What you need

- QGIS 3.34 LTR or newer
- Python 3.10 or newer
- An MCP client, such as Claude Desktop or Claude Code

## 1. The MCP server

Run it straight from PyPI:

```bash
uvx qgis-mcp
```

Or install it once:

```bash
pipx install qgis-mcp
```

Both give you a `qgis-mcp` command. Your MCP client starts it; you do not run it
by hand.

## 2. The QGIS plugin

Download `qgis_mcp_plugin-<version>.zip` from the
[latest release](https://github.com/jtdub/qgis-mcp/releases/latest).

In QGIS, open `Plugins` > `Manage and Install Plugins` > `Install from ZIP`,
choose the file, and install it.

Then open the `Installed` tab and tick **QGIS MCP**.

## 3. Point your client at the server

Add the server to your client configuration. For Claude Desktop, edit
`claude_desktop_config.json`:

```json
{
    "mcpServers": {
        "qgis": {
            "command": "uvx",
            "args": ["qgis-mcp"]
        }
    }
}
```

Restart the client.

## 4. Start the plugin server

In QGIS, open `Plugins` > `QGIS MCP`. The dock appears. Click **Start Server**.

The plugin binds `127.0.0.1:9876`, generates a token, and writes the host, the
port, and the token to a session file inside your QGIS profile. The MCP server
finds that file by itself.

## 5. Check it works

Ask your assistant to ping QGIS. `ping` returns the protocol version, the plugin
version, the QGIS version, and whether `execute_code` is allowed.

If the versions do not match, read [Upgrade](upgrade.md).

## Install from a clone instead

```bash
git clone git@github.com:jtdub/qgis-mcp.git
```

Copy `qgis_mcp_plugin/` into your QGIS profile plugins folder. Find it in QGIS
at `Settings` > `User profiles` > `Open active profile folder`, then
`python/plugins`.

Point your client at the clone:

```json
{
    "mcpServers": {
        "qgis": {
            "command": "uv",
            "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/qgis-mcp", "qgis-mcp"]
        }
    }
}
```
