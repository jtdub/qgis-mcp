# Overview

QGIS MCP gives an AI assistant a set of tools that act on a running QGIS
Desktop session. The assistant does not screen-scrape and does not drive the
mouse. It calls a tool, and a handler inside QGIS runs a PyQGIS call.

## What the tools cover

| Group | Does |
| --- | --- |
| Project | Create, load, and save a project |
| Introspection | List layers, read fields, read distinct values, sample features, read an extent |
| Filtering | Filter by expression into a new layer, trace a river network downstream |
| Styling | Single symbol, graduated, categorized, and labels |
| Cartography | Build a print layout with a legend and an inset map, then export it |
| Canvas | Set the extent, toggle visibility, render an image |
| Escape hatch | Run a processing algorithm, or arbitrary PyQGIS |

[The tool reference](tool_reference.md) lists every tool with its parameters.

## Two rules that shape every tool

**Every coordinate is WGS84.** You give the assistant longitude and latitude in
degrees, and every extent it reports comes back the same way. The plugin
reprojects to and from the layer CRS for you. You never convert by hand.

**A layer is named by its name.** A layer id from `list_layers` also works, so
the assistant can use whichever it holds.

## What the assistant sees

A read tool returns structured data with a published schema, so the assistant
does not parse text. A result that could be long comes back one page at a time,
and carries `has_more` and `offset`.

## What it cannot do

- It cannot edit feature geometry or attributes. Only `filter_layer` and
  `execute_code` write features.
- It cannot save a memory layer to disk. A layer built by `filter_layer` lives
  only for the session.
- It cannot add a basemap.

[The FAQ](faq.md) covers the workarounds.
