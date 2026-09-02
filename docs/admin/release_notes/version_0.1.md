# v0.1 Release Notes

The tools that came before the 0.2 series. This history was written by
hand, before the project adopted towncrier.

## [v0.1.0] — Initial Release (upstream)

### Phase 1 — Introspection Tools
- Enhanced `list_layers` (formerly `get_layers`) with full field metadata, CRS, geometry type
- Added `get_layer_fields` — detailed field info (type, length, precision)
- Added `get_unique_values` — unique values for a field with limit
- Added `sample_features` — sample features with optional expression filter
- Added `get_layer_extent` — bounding box in WGS84

### Phase 2 — Filtering & Spatial Operations
- Added `filter_layer` — expression-based layer filtering to memory layer
- Added `trace_downstream` — network topology tracing (HydroSHEDS compatible)
- Added `set_layer_visibility` — toggle layer visibility
- Added `set_canvas_extent` — set map canvas extent in WGS84

### Phase 3 — Styling
- Added `style_line_graduated` — graduated line width by field value
- Added `style_simple` — simple single-symbol styling
- Added `style_categorized` — categorized styling by field with color ramp
- Added `add_labels` — labeling with line-following and buffer support

### Phase 4 — Print Layout & Cartography
- Added `create_print_layout` — create print layout with map, title, scale bar, north arrow
- Added `add_legend` — add filtered legend to layout
- Added `add_inset_map` — add inset/overview map with extent indicator
- Added `export_layout` — export layout to PDF or image

### Phase 5 — Hardening
- Socket reconnection logic
- WGS84 default CRS handling for all coordinate I/O
- Improved error messages with layer name validation
- JSON framing improvements for large payloads

## [0.1.0] — Initial Release (upstream)

### Tools
- `ping` — connection test
- `get_qgis_info` — QGIS version and profile info
- `create_new_project` — create and save new project
- `load_project` — load QGIS project file
- `get_project_info` — project metadata and layer list
- `save_project` — save current project
- `add_vector_layer` — add vector layer
- `add_raster_layer` — add raster layer
- `get_layers` — list all layers
- `remove_layer` — remove layer by ID
- `zoom_to_layer` — zoom to layer extent
- `get_layer_features` — get vector features with limit
- `execute_processing` — run QGIS Processing algorithms
- `render_map` — export map as image
- `execute_code` — execute arbitrary PyQGIS code
