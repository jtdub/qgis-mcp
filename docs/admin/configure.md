# Configure

## Authentication

Every request carries a token. The plugin generates a new one each time you
click **Start Server**, and writes it to a session file inside your QGIS
profile:

```
<QGIS profile>/qgis_mcp/session.json
```

The file holds the host, the port, the token, and the process id. It is created
with mode `0600`, inside a directory with mode `0700`. The MCP server reads it
by itself, so you normally set nothing.

WARNING: The token is a credential. Do not paste it into a chat or an issue.

If the MCP server cannot find the file, copy the token from the dock and set it
in the environment:

```json
{
    "mcpServers": {
        "qgis": {
            "command": "uvx",
            "args": ["qgis-mcp"],
            "env": { "QGIS_MCP_TOKEN": "the-token-from-the-dock" }
        }
    }
}
```

## Environment variables

These override the session file.

| Variable | Purpose | Default |
| --- | --- | --- |
| `QGIS_MCP_HOST` | The host the plugin listens on | `127.0.0.1` |
| `QGIS_MCP_PORT` | The port | `9876` |
| `QGIS_MCP_TOKEN` | The token | read from the session file |
| `QGIS_MCP_SESSION_FILE` | An explicit path to the session file | the default profile |

## The port

Change the port in the dock before you start the server. Use this when 9876 is
taken, or when you run two QGIS windows.

The plugin binds `127.0.0.1` only. Nothing outside your machine can reach it.

## The execute_code gate

`execute_code` runs arbitrary Python inside the QGIS process, with your file
access. It is off by default.

WARNING: Code that runs through this tool can read and delete any file you can.
Tick the box only while you need it, and untick it after.

Tick **Allow execute_code (runs arbitrary Python)** in the dock to allow it. The
setting applies at once, and it applies to a running server. It is not saved
between sessions.

`ping` and `get_qgis_info` report whether it is allowed, so an assistant can
tell you what it may do.

## Limits

These are fixed. They stop one request from exhausting memory or filling an
assistant's context.

| Limit | Value |
| --- | --- |
| Largest request | 8 MB |
| Largest response | 50 MB |
| Features in one result | 1000 |
| Characters of geometry text per feature | 200 |
| Seconds before the client gives up on a response | 120 |

## Two QGIS windows

Each window needs its own port. Both write to the same session file if they
share a profile, so the second one to start wins. Use a separate QGIS profile
for each, or set `QGIS_MCP_PORT` and `QGIS_MCP_TOKEN` on the client.
