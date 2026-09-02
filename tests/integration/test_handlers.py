"""Handler tests that run against a real QGIS.

Each test calls a plugin handler directly. The socket is not involved.
"""

import pytest
from conftest import add_layer, build_layer, layers_named
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsGraduatedSymbolRenderer,
    QgsProject,
    QgsSingleSymbolRenderer,
)


class TestListLayers:
    def test_a_vector_layer_reports_its_fields_and_count(self, plugin, cities):
        listed = {layer["name"]: layer for layer in plugin.list_layers()}

        assert listed["cities"]["type"] == "vector"
        assert listed["cities"]["geometry_type"] == "Point"
        assert listed["cities"]["feature_count"] == 5
        assert listed["cities"]["crs"] == "EPSG:4326"
        assert [field["name"] for field in listed["cities"]["fields"]] == ["name", "pop"]

    def test_an_empty_project_lists_nothing(self, plugin):
        assert plugin.list_layers() == []


class TestGetLayerFields:
    def test_every_field_carries_its_storage_limits(self, plugin, cities):
        fields = plugin.get_layer_fields("cities")["fields"]

        assert [field["name"] for field in fields] == ["name", "pop"]
        assert all("length" in field and "precision" in field for field in fields)

    def test_a_missing_layer_names_the_layers_on_offer(self, plugin, cities):
        with pytest.raises(Exception, match="Available layers"):
            plugin.get_layer_fields("absent")


class TestGetUniqueValues:
    def test_the_values_are_the_true_sorted_set(self, plugin, cities):
        result = plugin.get_unique_values("cities", "name")

        assert result["values"] == ["Arequipa", "Cusco", "Lima", "Puno"]
        assert result["total_count"] == 4
        assert result["returned_count"] == 4
        assert result["has_more"] is False

    def test_null_is_left_out(self, plugin, cities):
        assert None not in plugin.get_unique_values("cities", "name")["values"]

    def test_a_page_reports_that_more_follows(self, plugin, cities):
        page = plugin.get_unique_values("cities", "name", limit=2)

        assert page["values"] == ["Arequipa", "Cusco"]
        assert page["total_count"] == 4
        assert page["has_more"] is True

    def test_the_next_page_continues_the_sorted_set(self, plugin, cities):
        page = plugin.get_unique_values("cities", "name", limit=2, offset=2)

        assert page["values"] == ["Lima", "Puno"]
        assert page["offset"] == 2
        assert page["has_more"] is False

    def test_the_pages_together_are_the_whole_set(self, plugin, cities):
        whole = plugin.get_unique_values("cities", "name")["values"]
        first = plugin.get_unique_values("cities", "name", limit=3)["values"]
        second = plugin.get_unique_values("cities", "name", limit=3, offset=3)["values"]

        assert first + second == whole

    def test_a_missing_field_names_the_fields_on_offer(self, plugin, cities):
        with pytest.raises(Exception, match="Available fields"):
            plugin.get_unique_values("cities", "absent")

    def test_a_raster_layer_is_refused(self, plugin, tmp_path):
        from qgis.core import QgsRasterLayer

        layer = QgsRasterLayer(str(tmp_path / "absent.tif"), "dem")
        layer.setName("dem")
        QgsProject.instance().addMapLayer(layer, False)
        QgsProject.instance().addMapLayer(layer)

        with pytest.raises(Exception, match="not a vector layer"):
            plugin.get_unique_values("dem", "band")


class TestSampleFeatures:
    def test_the_geometry_comes_back_as_wgs84_wkt(self, plugin, cities):
        feature = plugin.sample_features("cities", count=1)["features"][0]

        assert feature["geometry_wkt"].startswith("Point")
        assert "-71.97" in feature["geometry_wkt"] or "-77.04" in feature["geometry_wkt"]

    def test_an_expression_filters_the_features(self, plugin, cities):
        result = plugin.sample_features("cities", count=10, expression='"pop" > 1000000')

        assert result["returned_count"] == 1
        assert result["features"][0]["attributes"]["name"] == "Lima"

    def test_a_broken_expression_is_reported(self, plugin, cities):
        with pytest.raises(Exception, match="Invalid expression"):
            plugin.sample_features("cities", expression="this is not an expression")

    def test_a_short_page_says_more_follows(self, plugin, cities):
        page = plugin.sample_features("cities", count=2)

        assert page["returned_count"] == 2
        assert page["total_count"] == 5
        assert page["has_more"] is True

    def test_the_last_page_says_nothing_follows(self, plugin, cities):
        page = plugin.sample_features("cities", count=2, offset=3)

        assert page["returned_count"] == 2
        assert page["has_more"] is False

    def test_offset_skips_the_earlier_features(self, plugin, cities):
        first = plugin.sample_features("cities", count=5)["features"]
        rest = plugin.sample_features("cities", count=5, offset=2)["features"]

        assert [feature["id"] for feature in rest] == [feature["id"] for feature in first[2:]]

    def test_a_null_attribute_comes_back_as_none(self, plugin, cities):
        names = [item["attributes"]["name"] for item in plugin.sample_features("cities", count=10)["features"]]

        assert None in names

    def test_a_long_geometry_is_truncated(self, plugin):
        points = ", ".join(f"{-72 + index / 1000.0} -13" for index in range(400))
        layer = add_layer(build_layer("LineString?field=name:string(10)", "long", [(f"LINESTRING({points})", ["a"])]))
        assert layer.featureCount() == 1

        wkt = plugin.sample_features("long", count=1)["features"][0]["geometry_wkt"]

        assert wkt.endswith("...")
        assert len(wkt) == plugin.MAX_WKT_CHARS + 3


class TestGetLayerExtent:
    def test_a_wgs84_layer_keeps_its_coordinates(self, plugin, cities):
        extent = plugin.get_layer_extent("cities")

        assert extent["xmin"] == pytest.approx(-77.04, abs=0.01)
        assert extent["ymax"] == pytest.approx(-12.05, abs=0.01)

    def test_a_projected_layer_is_reported_in_degrees(self, plugin):
        rows = [("POINT(500000 8500000)", ["a"])]
        add_layer(build_layer("Point?field=name:string(10)", "utm", rows, crs="EPSG:32718"))

        extent = plugin.get_layer_extent("utm")

        assert -180 <= extent["xmin"] <= 180
        assert -90 <= extent["ymin"] <= 90


class TestFilterLayer:
    def test_the_output_layer_holds_the_matching_features(self, plugin, cities):
        result = plugin.filter_layer("cities", '"pop" > 500000', "big")

        assert result["feature_count"] == 2
        output = layers_named("big")[0]
        assert output.featureCount() == 2

    def test_the_output_layer_is_wgs84(self, plugin, cities):
        plugin.filter_layer("cities", '"pop" > 0', "copy")

        assert layers_named("copy")[0].crs().authid() == "EPSG:4326"

    def test_the_output_keeps_the_source_fields(self, plugin, cities):
        plugin.filter_layer("cities", '"pop" > 0', "copy")

        output = layers_named("copy")[0]
        assert [field.name() for field in output.fields()] == ["name", "pop"]

    def test_a_broken_expression_is_reported(self, plugin, cities):
        with pytest.raises(Exception, match="Invalid expression"):
            plugin.filter_layer("cities", "not an expression", "out")

    def test_a_batch_larger_than_one_write_is_copied_whole(self, plugin):
        count = plugin.FEATURE_BATCH_SIZE * 2 + 7
        rows = [(f"POINT(-72 {-13 - index / 100000.0})", [index]) for index in range(count)]
        add_layer(build_layer("Point?field=n:integer", "many", rows))

        result = plugin.filter_layer("many", '"n" >= 0', "many_copy")

        assert result["feature_count"] == count
        assert layers_named("many_copy")[0].featureCount() == count


class TestTraceDownstream:
    def test_the_trace_follows_the_next_down_pointers(self, plugin, rivers):
        result = plugin.trace_downstream("rivers", -72.0, -13.5, output_name="traced")

        assert result["segments_traced"] == 4
        assert result["start_segment_id"] == 10
        assert result["end_segment_id"] == 40

    def test_the_trace_starts_at_the_nearest_segment(self, plugin, rivers):
        result = plugin.trace_downstream("rivers", -72.21, -13.71, output_name="traced")

        assert result["start_segment_id"] == 30
        assert result["segments_traced"] == 2

    def test_a_separate_network_is_not_followed(self, plugin, rivers):
        result = plugin.trace_downstream("rivers", -70.0, -15.0, output_name="traced")

        assert result["start_segment_id"] == 90
        assert result["segments_traced"] == 1

    def test_the_output_layer_holds_the_traced_geometry(self, plugin, rivers):
        plugin.trace_downstream("rivers", -72.0, -13.5, output_name="traced")

        output = layers_named("traced")[0]
        assert output.featureCount() == 4
        assert output.crs().authid() == "EPSG:4326"

    def test_a_cycle_does_not_loop_forever(self, plugin):
        rows = [
            ("LINESTRING(-72.0 -13.5, -72.1 -13.6)", [1, 2]),
            ("LINESTRING(-72.1 -13.6, -72.2 -13.7)", [2, 1]),
        ]
        add_layer(build_layer("LineString?field=HYRIV_ID:integer&field=NEXT_DOWN:integer", "loop", rows))

        result = plugin.trace_downstream("loop", -72.0, -13.5, output_name="traced")

        assert result["segments_traced"] == 2

    def test_a_missing_id_field_names_the_fields_on_offer(self, plugin, rivers):
        with pytest.raises(Exception, match="Available fields"):
            plugin.trace_downstream("rivers", -72.0, -13.5, id_field="ABSENT")


class TestStyling:
    def test_style_simple_sets_a_single_symbol_renderer(self, plugin, cities):
        plugin.style_simple("cities", color="#ff0000")

        assert isinstance(cities.renderer(), QgsSingleSymbolRenderer)

    def test_style_simple_sets_the_opacity(self, plugin, cities):
        plugin.style_simple("cities", opacity=0.5)

        assert cities.opacity() == pytest.approx(0.5)

    def test_style_categorized_makes_one_class_for_each_value(self, plugin, rivers):
        result = plugin.style_categorized("rivers", "name")

        assert isinstance(rivers.renderer(), QgsCategorizedSymbolRenderer)
        assert result["categories"] == 3
        assert len(rivers.renderer().categories()) == 3

    def test_style_line_graduated_uses_equal_intervals(self, plugin, rivers):
        result = plugin.style_line_graduated("rivers", "ORD_STRA", num_classes=4)

        renderer = rivers.renderer()
        assert isinstance(renderer, QgsGraduatedSymbolRenderer)
        assert result["classes"] == 4
        assert len(renderer.ranges()) == 4
        widths = [item.upperValue() - item.lowerValue() for item in renderer.ranges()]
        assert widths == pytest.approx([widths[0]] * 4)

    def test_style_line_graduated_defaults_to_five_classes(self, plugin, rivers):
        result = plugin.style_line_graduated("rivers", "ORD_STRA")

        assert result["classes"] == plugin.DEFAULT_GRADUATED_CLASSES

    def test_style_line_graduated_reports_the_true_range(self, plugin, rivers):
        result = plugin.style_line_graduated("rivers", "ORD_STRA")

        assert result["value_range"] == {"min": 1, "max": 4}

    def test_a_single_valued_field_cannot_be_graduated(self, plugin):
        rows = [("LINESTRING(-72 -13, -72.1 -13.1)", [7]), ("LINESTRING(-72 -14, -72.1 -14.1)", [7])]
        add_layer(build_layer("LineString?field=ORD_STRA:integer", "flat", rows))

        with pytest.raises(Exception, match="single value"):
            plugin.style_line_graduated("flat", "ORD_STRA")

    def test_add_labels_turns_labels_on(self, plugin, rivers):
        plugin.add_labels("rivers", "name")

        assert rivers.labelsEnabled() is True
        assert rivers.labeling().settings().fieldName == "name"

    def test_add_labels_rejects_a_missing_field(self, plugin, rivers):
        with pytest.raises(Exception, match="Available fields"):
            plugin.add_labels("rivers", "absent")


class TestLayerIdentity:
    def test_remove_layer_accepts_a_name(self, plugin, cities):
        plugin.remove_layer("cities")

        assert layers_named("cities") == []

    def test_remove_layer_accepts_an_id(self, plugin, cities):
        plugin.remove_layer(cities.id())

        assert layers_named("cities") == []

    def test_get_layer_features_accepts_a_name(self, plugin, cities):
        assert plugin.get_layer_features("cities")["returned_count"] == 5

    def test_get_layer_features_accepts_an_id(self, plugin, cities):
        assert plugin.get_layer_features(cities.id())["returned_count"] == 5

    def test_get_layer_features_reports_the_layer_name(self, plugin, cities):
        assert plugin.get_layer_features(cities.id())["layer_name"] == "cities"

    def test_get_layer_features_pages(self, plugin, cities):
        page = plugin.get_layer_features("cities", limit=2, offset=1)

        assert page["returned_count"] == 2
        assert page["offset"] == 1
        assert page["has_more"] is True

    def test_zoom_to_layer_accepts_a_name(self, plugin, cities):
        assert plugin.zoom_to_layer("cities")["zoomed_to"] == cities.id()

    def test_an_unknown_layer_names_both_the_names_and_the_ids(self, plugin, cities):
        with pytest.raises(Exception) as failure:
            plugin.remove_layer("absent")

        assert "Available layers" in str(failure.value)
        assert "Available ids" in str(failure.value)


class TestCanvas:
    def test_set_layer_visibility_unchecks_the_tree_node(self, plugin, cities):
        plugin.set_layer_visibility("cities", False)

        node = QgsProject.instance().layerTreeRoot().findLayer(cities.id())
        assert node.isVisible() is False

    def test_set_canvas_extent_moves_the_canvas(self, plugin, iface, cities):
        plugin.set_canvas_extent(-73.0, -14.0, -71.0, -13.0)

        extent = iface.mapCanvas().extent()
        assert extent.xMinimum() < -71.0
        assert extent.xMaximum() > -73.0


class TestPrintLayout:
    def test_a_layout_is_created_with_a_main_map(self, plugin):
        result = plugin.create_print_layout("Map1")

        assert result["page_size"] == "A3"
        layout = plugin._find_layout("Map1")
        assert layout.itemById("main") is not None

    def test_a_duplicate_name_is_refused(self, plugin):
        plugin.create_print_layout("Map1")

        with pytest.raises(Exception, match="already exists"):
            plugin.create_print_layout("Map1")

    def test_replace_overwrites_the_layout(self, plugin):
        plugin.create_print_layout("Map1", page_size="A3")

        result = plugin.create_print_layout("Map1", page_size="A4", replace=True)

        assert result["page_size"] == "A4"

    def test_a_missing_layout_names_the_layouts_on_offer(self, plugin):
        plugin.create_print_layout("Map1")

        with pytest.raises(Exception, match="Available layouts"):
            plugin._find_layout("Map2")

    def test_a_legend_is_added(self, plugin, cities):
        plugin.create_print_layout("Map1")

        result = plugin.add_legend("Map1", title="Key")

        assert result["title"] == "Key"

    def test_a_legend_finds_a_map_item_that_has_no_main_id(self, plugin, cities):
        from qgis.core import QgsLayoutItemMap, QgsPrintLayout

        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("ByHand")
        layout.addLayoutItem(QgsLayoutItemMap(layout))
        project.layoutManager().addLayout(layout)

        assert plugin.add_legend("ByHand")["layout_name"] == "ByHand"

    def test_a_layout_with_no_map_is_reported(self, plugin):
        from qgis.core import QgsPrintLayout

        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        layout.setName("Bare")
        project.layoutManager().addLayout(layout)

        with pytest.raises(Exception, match="no map item"):
            plugin.add_legend("Bare")

    def test_an_inset_map_is_added(self, plugin, cities):
        plugin.create_print_layout("Map1")

        result = plugin.add_inset_map("Map1", extent=[-78, -17, -68, -11])

        assert result["extent"] == [-78, -17, -68, -11]

    def test_the_layout_exports_to_png(self, plugin, cities, tmp_path):
        plugin.create_print_layout("Map1", title="Peru")
        target = tmp_path / "map.png"

        result = plugin.export_layout("Map1", str(target), dpi=72)

        assert target.exists()
        assert result["file_size_bytes"] > 0
        assert result["format"] == "png"


class TestRenderMap:
    def _colours(self, path):
        """Return the distinct pixel colours of a saved image."""
        from qgis.PyQt.QtGui import QImage

        image = QImage(str(path))
        assert not image.isNull()
        return {image.pixel(x, y) for x in range(0, image.width(), 8) for y in range(0, image.height(), 8)}

    def test_an_empty_canvas_renders_a_blank_image(self, plugin, iface, regions, tmp_path):
        iface.mapCanvas().setExtent(regions.extent())
        iface.mapCanvas().setLayers([])
        target = tmp_path / "blank.png"

        plugin.render_map(str(target), width=64, height=64)

        assert len(self._colours(target)) == 1

    def test_the_canvas_layer_set_decides_what_is_drawn(self, plugin, iface, regions, tmp_path):
        plugin.style_simple("regions", color="#ff0000", outline_color="#ff0000")
        iface.mapCanvas().setExtent(regions.extent())
        iface.mapCanvas().setLayers([regions])
        target = tmp_path / "drawn.png"

        plugin.render_map(str(target), width=64, height=64)

        assert len(self._colours(target)) > 1

    def test_a_project_layer_off_the_canvas_is_not_drawn(self, plugin, iface, regions, tmp_path):
        plugin.style_simple("regions", color="#ff0000", outline_color="#ff0000")
        iface.mapCanvas().setExtent(regions.extent())
        iface.mapCanvas().setLayers([])
        target = tmp_path / "hidden.png"

        plugin.render_map(str(target), width=64, height=64)

        assert len(self._colours(target)) == 1


class TestExecuteCode:
    def test_the_gate_is_shut_by_default(self, plugin):
        with pytest.raises(Exception, match="execute_code is disabled"):
            plugin.execute_code("pass")

    def test_the_code_sees_the_project(self, plugin_with_code):
        result = plugin_with_code.execute_code("print(QgsProject.instance().count())")

        assert result["executed"] is True
        assert result["stdout"].strip() == "0"

    def test_a_failure_returns_the_traceback(self, plugin_with_code):
        result = plugin_with_code.execute_code("raise RuntimeError('boom')")

        assert result["executed"] is False
        assert "RuntimeError" in result["traceback"]


class TestQgisInfo:
    def test_ping_reports_the_running_qgis(self, plugin):
        info = plugin.ping()

        assert info["pong"] is True
        assert info["qgis_version"]
        assert info["execute_code_enabled"] is False

    def test_get_qgis_info_reports_the_profile(self, plugin):
        info = plugin.get_qgis_info()

        assert info["qgis_version"]
        assert info["profile_folder"]
