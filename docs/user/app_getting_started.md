# Getting started

This page takes you from an empty QGIS window to an exported map.

## Before you start

Install both sides, and start the plugin server. Read
[Install](../admin/install.md) if you have not done that yet.

## 1. Learn what is loaded

Ask the assistant to list the layers. It calls `list_layers`, which reports
every layer with its CRS, its geometry type, its feature count, and its fields.

Start here every time. The assistant cannot write a correct expression until it
knows the field names.

## 2. Read the field values

Before the assistant filters on a field, it reads what that field holds:

- `get_layer_fields` gives the type and the length of each field.
- `get_unique_values` gives the distinct values, sorted, one page at a time.
- `sample_features` gives a few whole features, with geometry as WGS84 text.

A guessed value produces an empty filter. A read value does not.

## 3. Filter

`filter_layer` copies the features that match a QGIS expression into a new
memory layer, in WGS84, and adds it to the project.

```
"population" > 100000
"name" IN ('Cusco', 'Arequipa')
```

The result layer lives only for the session. Save the project, or use
`execute_code`, to keep it.

## 4. Style

- `style_simple` sets one symbol for the whole layer.
- `style_categorized` gives each distinct value its own colour.
- `style_line_graduated` scales line width by a numeric field, in equal
  intervals.
- `add_labels` turns on labels, and follows the line for a line layer.

## 5. Frame the map

`set_canvas_extent` takes a WGS84 bounding box. `zoom_to_layer` frames one
layer. The print layout copies the canvas extent, so set it before you build
the layout.

## 6. Build and export

```
create_print_layout  → add_legend → add_inset_map → export_layout
```

`create_print_layout` builds a page with a map, a scale bar, and a north arrow.
It refuses to overwrite a layout of the same name unless you pass `replace`.

`export_layout` writes a PDF or an image. The extension decides which.

## A worked request

> Load the rivers layer, keep only the ones of order 4 or higher, colour them by
> name, label them, and export an A3 map called Peru Rivers.

The assistant runs roughly this:

1. `list_layers`
2. `get_layer_fields` on the rivers layer
3. `get_unique_values` on the order field
4. `filter_layer` with `"ORD_STRA" >= 4`
5. `style_categorized` on the name field
6. `add_labels` on the name field
7. `zoom_to_layer`
8. `create_print_layout` with a title
9. `add_legend`
10. `export_layout` to a PDF

Read [Use cases](app_use_cases.md) for more.
