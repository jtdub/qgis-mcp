# Upgrade

The MCP server and the QGIS plugin check that they speak the same protocol.
Upgrade both, from the same release.

## The symptom of a mismatch

The assistant reports something like:

```
The QGIS MCP plugin speaks protocol 1 and this server speaks 2.
Copy the current qgis_mcp_plugin folder into your QGIS profile, then restart QGIS.
```

The check runs when the server connects, so you see it at once, not halfway
through a task.

## Steps

1. Stop the plugin server in the dock.
2. Upgrade the package.

    ```bash
    pipx upgrade qgis-mcp
    ```

    `uvx qgis-mcp` fetches the newest version by itself.

3. Download `qgis_mcp_plugin-<version>.zip` from the same release.
4. In QGIS, `Plugins` > `Manage and Install Plugins` > `Install from ZIP`.
   Installing over an existing plugin replaces it.
5. Restart QGIS.
6. Open the dock and click **Start Server**.
7. Ask the assistant to call `get_qgis_info`. Confirm `plugin_version` and
   `server_version` read the same number.

## What can change between releases

Read the [release notes](release_notes/index.md) before you upgrade. A release
that changes the wire format bumps the protocol version, and both sides must
move together.

A tool can also change its parameters. The release notes name any tool that
changed.
