# Adding a tool

Every new tool changes **both** processes. The MCP server publishes the tool.
The plugin runs the PyQGIS.

## 1. The plugin handler

Add a method to `QgisMCPServer` in `qgis_mcp_plugin/qgis_mcp_plugin.py`, then
register it in the `handlers` dict inside `execute_command()`.

```python
def buffer_layer(self, layer_name, distance, output_name, **kwargs):
    """Build a buffer around every feature of a layer."""
    layer = self._require_vector(self._resolve_layer(layer_name), layer_name)
    ...
```

Rules for a handler:

- Accept `**kwargs`. A newer client may send a parameter this version ignores.
- Resolve a layer with `_resolve_layer()`. It takes a name or an id, and its
  error names every name and id in the project.
- Check the type with `_require_vector()`, and a field with `_field_index()`.
  Both raise a message that lists what was available.
- Every coordinate in and out is WGS84. Use `_rect_to_wgs84()`,
  `_point_from_wgs84()`, and `_transform()`.
- Build a `QgsCoordinateTransform` once with `_transform()`. Never build one
  inside a per-feature loop.
- Call `_pump_ui()` freely inside a long loop. It throttles itself, so no
  handler picks a rate.
- Return a plain dictionary. It must be JSON serializable.

## 2. The MCP tool

Add an `async` function to `src/qgis_mcp/qgis_mcp_server.py`.

A **read** tool returns a model, so the client gets a published output schema:

```python
@mcp.tool(annotations=_annotate("Buffer Layer"))
async def buffer_layer(layer_name: str, distance: float, output_name: str) -> LayerRef:
    """Build a buffer around every feature of a layer."""
    return await _run_as(LayerRef, "buffer_layer", {...})
```

A **write** tool returns compact JSON:

```python
    return await _run_json("buffer_layer", {...})
```

Rules for a tool:

- Never block the event loop. Every QGIS call goes through `_run`, `_run_as`, or
  `_run_json`, which run on a worker thread.
- Add `ctx: Context` only when the tool reports progress. Use `_run_watched`
  for a slow tool.
- Set the annotations. `_annotate` takes `read_only`, `destructive`,
  `idempotent`, and `open_world`. A client shows these to the user.

## 3. The output model

A read tool needs a `TypedDict` in `src/qgis_mcp/models.py`.

WARNING: A key the model does not declare is dropped from the structured result,
silently. Declare every key the handler returns.

The end to end suite asserts the exact key set for each model, which is what
catches a drift between the two.

## 4. Pagination

A result that can be long carries four keys: `offset`, `returned_count`,
`total_count`, and `has_more`. Use `_page_bounds()` and `_feature_page()`.

`total_count` must describe the same set as `has_more`. A filtered page counts
the matching features, not the layer.

## 5. The protocol version

Bump `PROTOCOL_VERSION` in **both** files when the wire format changes. Adding a
tool does not change the wire format. Changing the request or response envelope
does.

A test asserts the two constants agree.

## 6. Tests

- A unit test in `tests/test_mcp_tools.py` that the tool sends the right
  command with the right parameters.
- A handler test in `tests/integration/test_handlers.py`, against real layers.
  Build them with `build_layer()` from `conftest.py`.
- An end to end test in `tests/integration/test_end_to_end.py` for a read tool,
  asserting the key set.

## 7. Documentation

- Add the tool to [the tool reference](../user/tool_reference.md).
- Update the tool count in `tests/test_tool_annotations.py`.
- Add a fragment under `changes/`.
