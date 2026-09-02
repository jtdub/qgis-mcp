# Frequently asked questions

## The assistant says it cannot connect to QGIS

Three things must be true.

1. QGIS is running, and the QGIS MCP plugin is enabled.
2. The dock is open, and you clicked **Start Server**.
3. The MCP server reads the same port and token.

The plugin writes the host, the port, and the token to a session file inside
your QGIS profile. The MCP server finds that file by itself. Read
[Configure](../admin/configure.md) if it cannot.

## It connected, then stopped working

You probably restarted the plugin server. The token changes each time it
starts. The MCP server reads the session file again and reconnects by itself.
If it does not, restart your MCP client.

## It says the plugin speaks a different protocol

The package and the plugin ship together, and they check each other at startup.
Copy the plugin folder from the same release as the package, then restart QGIS.
Read [Upgrade](../admin/upgrade.md).

## A tool says my layer does not exist

The error lists every layer name and every layer id in the project. Read it: the
name is usually different from what you expected, often by case or a space.

## The values from `get_unique_values` look incomplete

They are one page. The result carries `total_count` and `has_more`. Ask for the
next page with `offset`.

## Why is everything in degrees?

Every coordinate in and out is WGS84 (EPSG:4326). The plugin reprojects to and
from the layer CRS. One rule removes a whole class of error, and you never have
to say which CRS you meant.

## My filtered layer disappeared

`filter_layer` and `trace_downstream` build memory layers. They live only for
the QGIS session. Save the project to keep them, or write them to disk with
`execute_code`.

## The rendered image does not match my screen

It should. `render_map` draws the layers on the canvas, at the canvas extent.
If it looks wrong, check that the layer is visible in the layer tree.

## Can it add a basemap?

Not with a dedicated tool. Add an XYZ layer by hand in QGIS, or use
`execute_code`.

## Can it edit features?

No tool writes attributes or geometry. `filter_layer` copies features, and
`execute_code` can do anything. Editing tools are not built yet.

## Why is `execute_code` disabled?

It runs arbitrary Python inside your QGIS process, with your file access. It
stays off until you tick **Allow execute_code** in the dock, for that session
only. Turn it off when you are done.

## A long export seems to freeze QGIS

A handler runs on the QGIS main thread, so a long export or a long trace does
block the window. The plugin repaints during the long loops, but the window
stays busy. Wait for it.
