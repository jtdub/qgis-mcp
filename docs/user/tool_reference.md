# QGIS MCP Tools Reference

All coordinate inputs accept **WGS84 (EPSG:4326)**. All coordinate outputs are returned in **WGS84**.

Every tool that names a layer accepts a layer name or a layer id.

A result that carries `has_more` is one page. Read the next page with `offset`.

---

## Project Management

### `ping`
Check server connectivity.
- **Parameters:** None
- **Returns:** `{"pong": true}`

### `get_qgis_info`
Get QGIS version, profile folder, and plugin count.
- **Parameters:** None

### `create_new_project`
Create a new QGIS project and save it.
- **Parameters:** `path` (str, required)

### `load_project`
Load an existing QGIS project file.
- **Parameters:** `path` (str, required)

### `get_project_info`
Get current project metadata including filename, title, CRS, and layer summary.
- **Parameters:** None

### `save_project`
Save the current project.
- **Parameters:** `path` (str, optional — saves to current path if omitted)

---

## Layer Management

### `add_vector_layer`
Add a vector layer (shapefile, GeoJSON, GeoPackage, etc.).
- **Parameters:** `path` (str), `name` (str, optional), `provider` (str, default `"ogr"`)

### `add_raster_layer`
Add a raster layer (GeoTIFF, etc.).
- **Parameters:** `path` (str), `name` (str, optional), `provider` (str, default `"gdal"`)

### `remove_layer`
Remove a layer.
- **Parameters:** `layer` (str — a layer name or a layer id)

### `zoom_to_layer`
Zoom the map canvas to a layer's extent.
- **Parameters:** `layer` (str — a layer name or a layer id)

---

## Introspection

### `list_layers`
List all layers with rich metadata.
- **Parameters:** None
- **Returns:** Array of layer objects:
  ```json
  {
    "id": "layer_abc123",
    "name": "HydroRIVERS_v10",
    "type": "vector",
    "visible": true,
    "crs": "EPSG:4326",
    "geometry_type": "LineString",
    "feature_count": 245832,
    "fields": [
      {"name": "HYRIV_ID", "type": "Integer64"},
      {"name": "NEXT_DOWN", "type": "Integer64"}
    ]
  }
  ```
  Raster layers include `band_count`, `width`, `height`, `pixel_size`.

### `get_layer_fields`
Get detailed field information for a vector layer.
- **Parameters:** `layer_name` (str)
- **Returns:** Array of field objects with `name`, `type`, `length`, `precision`, `comment`

### `get_unique_values`
Read one sorted page of the distinct values a field holds.
- **Parameters:** `layer_name` (str), `field_name` (str), `limit` (int, default 50), `offset` (int, default 0)
- **Returns:** `values`, plus `total_count`, `returned_count`, `offset`, and `has_more`

### `sample_features`
Sample features from a layer with optional expression filter.
- **Parameters:** `layer_name` (str), `count` (int, default 5), `expression` (str, optional), `offset` (int, default 0)
- **Returns:** `features` with attributes and truncated WKT geometry, plus `total_count`, `returned_count`, `offset`, and `has_more`

### `get_layer_extent`
Get a layer's bounding box in WGS84.
- **Parameters:** `layer_name` (str)
- **Returns:** `{"xmin": -71.5, "ymin": -15.2, "xmax": -70.1, "ymax": -13.8}`

---

## Filtering & Spatial Operations

### `filter_layer`
Create a new memory layer from features matching an expression.
- **Parameters:** `layer_name` (str), `expression` (str), `output_name` (str)
- **Returns:** Feature count of new layer

### `trace_downstream`
Trace a river network downstream from a point.
- **Parameters:** `layer_name` (str), `start_lon` (float), `start_lat` (float), `id_field` (str, default `"HYRIV_ID"`), `next_down_field` (str, default `"NEXT_DOWN"`), `output_name` (str, default `"traced_river"`)
- **Returns:** Segment count

### `set_layer_visibility`
Toggle layer visibility.
- **Parameters:** `layer_name` (str), `visible` (bool)

### `set_canvas_extent`
Set the map canvas extent in WGS84 coordinates.
- **Parameters:** `xmin` (float), `ymin` (float), `xmax` (float), `ymax` (float)

---

## Styling

### `style_line_graduated`
Apply graduated line width styling based on a numeric field.
- **Parameters:** `layer_name` (str), `width_field` (str), `color` (str, default `"#1a5276"`), `min_width` (float, default 0.3), `max_width` (float, default 3.5), `num_classes` (int, default 0 = auto)
- **Returns:** Class count and value range

### `style_simple`
Apply simple single-symbol styling.
- **Parameters:** `layer_name` (str), `color` (str, default `"#333333"`), `outline_color` (str, default `"#000000"`), `width` (float, default 0.5), `opacity` (float, default 1.0)

### `style_categorized`
Apply categorized styling using a color ramp.
- **Parameters:** `layer_name` (str), `field_name` (str), `color_ramp` (str, default `"Spectral"`), `width` (float, default 1.0)
- **Returns:** Category count

### `add_labels`
Add labels to a layer.
- **Parameters:** `layer_name` (str), `field_name` (str), `font_size` (float, default 10), `color` (str, default `"#1a1a1a"`), `follow_line` (bool, default true), `buffer_size` (float, default 1.0), `font_family` (str, default `"Noto Sans"`)

---

## Print Layout & Cartography

### `create_print_layout`
Create a print layout with map, scale bar, and north arrow.
- **Parameters:** `name` (str), `page_size` (str, default `"A3"`), `orientation` (str, default `"landscape"`), `title` (str, optional), `replace` (bool, default false)
- **Returns:** Layout dimensions

WARNING: `replace` deletes the layout that already has this name. Without it, the tool reports an error instead.

### `add_legend`
Add a legend to a print layout. The legend links to the layout's main map item.
- **Parameters:** `layout_name` (str), `title` (str, default `"Legend"`), `position` (list, default `[15, 30]`), `width` (float, default 45), `layers` (list, optional — filter to specific layer names), `background` (bool, default true)

### `add_inset_map`
Add an inset/overview map to a print layout.
- **Parameters:** `layout_name` (str), `extent` (list `[xmin, ymin, xmax, ymax]` in WGS84), `position` (list, default `[320, 15]`), `size` (list, default `[80, 80]`), `layers` (list, optional), `show_extent_indicator` (bool, default true)

### `export_layout`
Export a print layout to PDF or image.
- **Parameters:** `layout_name` (str), `output_path` (str — extension determines format), `dpi` (int, default 300)
- **Returns:** Output path and file size

---

## Utilities

### `get_layer_features`
Read one page of features from a vector layer. Use `sample_features` to filter.
- **Parameters:** `layer` (str — a layer name or a layer id), `limit` (int, default 10), `offset` (int, default 0)
- **Returns:** The same shape as `sample_features`

### `execute_processing`
Run a QGIS Processing algorithm.
- **Parameters:** `algorithm` (str), `parameters` (dict)

### `render_map`
Render the current map canvas to an image file.
- **Parameters:** `path` (str), `width` (int, default 800), `height` (int, default 600)

### `execute_code`
Execute arbitrary PyQGIS code (escape hatch).
- **Parameters:** `code` (str)
- **Returns:** `stdout`, `stderr`, execution status
