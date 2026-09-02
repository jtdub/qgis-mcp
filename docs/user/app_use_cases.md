# Use cases

Each case names the tools in the order they run.

## Find out what a project holds

You inherited a project and do not know what is in it.

1. `get_project_info` — the file, the CRS, and how many layers.
2. `list_layers` — every layer, with fields and feature counts.
3. `get_layer_extent` — where a layer sits, in degrees.

## Explore a field before you filter

1. `get_layer_fields` — the field names and their types.
2. `get_unique_values` — the distinct values, sorted. Read the next page with
   `offset` while `has_more` is true.
3. `sample_features` — a few whole features, to see the shape of the data.

## Cut a large layer down

1. `get_unique_values` to learn the values.
2. `filter_layer` with an expression.
3. `zoom_to_layer` on the result.

The output is a memory layer in WGS84. It is gone when QGIS closes, unless you
save the project.

## Trace a river downstream

`trace_downstream` follows a network from a point, using an id field and a
"next downstream" pointer. It suits HydroSHEDS and HydroRIVERS data.

Give it a longitude and a latitude. It finds the nearest segment, walks the
pointers to the sea, and writes the traced segments to a new layer.

## Make a thematic map

1. `style_categorized` on a text field, or `style_line_graduated` on a number.
2. `add_labels`.
3. `set_canvas_extent` to frame the area.
4. `create_print_layout`, then `add_legend`.
5. `export_layout`.

## Add a locator inset

`add_inset_map` puts a small overview map on the layout, with a red rectangle
showing where the main map sits. Give it a wider WGS84 extent than the main map.

## Run a Processing algorithm

`execute_processing` runs anything in the Processing Toolbox. Give it the
algorithm id, such as `native:buffer`, and its parameter dictionary. A layer it
outputs comes back with an id and a name, so the next tool can use it.

## When no tool fits

`execute_code` runs PyQGIS inside QGIS. It is off until you tick
**Allow execute_code** in the dock. Prefer a real tool: `execute_code` returns
text, so the assistant cannot chain its result.
