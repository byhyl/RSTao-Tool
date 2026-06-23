"""矢量处理模块测试 — 修正版（匹配实际 API）"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from shapely.geometry import LineString, Point, Polygon

from core.vector_processing import (
    add_property_field,
    batch_update_properties,
    create_line_feature,
    create_new_layer,
    create_point_feature,
    create_polygon_feature,
    delete_property_field,
    geojson_to_shapely,
    move_feature,
    select_feature,
    shapely_to_geojson,
    update_feature_property,
)


class TestGeoJSONShapelyConversion:
    def test_point_roundtrip(self):
        gj = {"type": "Point", "coordinates": [116.4, 39.9]}
        geom = geojson_to_shapely(gj)
        assert isinstance(geom, Point)
        back = shapely_to_geojson(geom)
        assert back["type"] == "Point"

    def test_linestring_roundtrip(self):
        gj = {"type": "LineString", "coordinates": [[0, 0], [1, 1], [2, 0]]}
        geom = geojson_to_shapely(gj)
        assert isinstance(geom, LineString)
        back = shapely_to_geojson(geom)
        assert back["type"] == "LineString"

    def test_polygon_roundtrip(self):
        gj = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
        geom = geojson_to_shapely(gj)
        assert isinstance(geom, Polygon)

    def test_polygon_holes_roundtrip(self):
        gj = {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]],
            ],
        }
        geom = geojson_to_shapely(gj)
        assert len(geom.interiors) == 1
        back = shapely_to_geojson(geom)
        assert len(back["coordinates"]) == 2

    def test_invalid_type_raises(self):
        gj = {"type": "GeometryCollection", "geometries": []}
        with pytest.raises(Exception):
            geojson_to_shapely(gj)


class TestMoveFeature:
    def test_move_point(self):
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {},
        }
        moved = move_feature(feature, 10, 20)
        coords = moved["geometry"]["coordinates"]
        assert coords == pytest.approx([10, 20])

    def test_move_preserves_properties(self):
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [5, 5]},
            "properties": {"name": "test"},
        }
        moved = move_feature(feature, -3, 7)
        assert moved["properties"]["name"] == "test"


class TestCreateFeatures:
    def test_create_point(self):
        f = create_point_feature(100, 200, {"name": "P1"})
        assert f["geometry"]["type"] == "Point"
        assert f["properties"]["name"] == "P1"

    def test_create_point_default_props(self):
        f = create_point_feature(0, 0)
        assert "id" in f["properties"]

    def test_create_line(self):
        f = create_line_feature([(0, 0), (10, 10)])
        assert f["geometry"]["type"] == "LineString"

    def test_create_polygon(self):
        ring = [(0, 0), (10, 0), (10, 10), (0, 10)]
        f = create_polygon_feature(ring, {"area": 100})
        assert f["geometry"]["type"] == "Polygon"


class TestCreateNewLayer:
    def test_basic_layer(self):
        layer = create_new_layer("test_layer", "Point")
        assert layer["name"] == "test_layer"
        assert layer["features"] == []
        assert layer["visible"] is True

    def test_layer_has_color(self):
        layer = create_new_layer("roads", "LineString")
        assert "color" in layer

    def test_different_geometry_types(self):
        for gtype in ["Point", "LineString", "Polygon"]:
            layer = create_new_layer(gtype, gtype)
            assert layer["name"] == gtype


class TestPropertyFields:
    def test_add_field(self):
        layer = create_new_layer("test", "Point")
        updated = add_property_field(layer, "height", "float")
        assert "height" in updated["schema"]["properties"]

    def test_delete_field(self):
        layer = create_new_layer("test", "Point")
        layer = add_property_field(layer, "temp")
        updated = delete_property_field(layer, "temp")
        assert "temp" not in updated["schema"]["properties"]

    def test_update_feature_property(self):
        feature = create_point_feature(0, 0, {"count": 1})
        updated = update_feature_property(feature, "count", 5)
        assert updated["properties"]["count"] == 5

    def test_batch_update(self):
        layer = create_new_layer("points", "Point")
        layer["features"] = [
            create_point_feature(0, 0, {"status": "old"}),
            create_point_feature(1, 1, {"status": "old"}),
        ]
        result = batch_update_properties(layer, "status", "new")
        for f in result["features"]:
            assert f["properties"]["status"] == "new"


class TestSelectFeature:
    def test_select_by_point(self):
        layer = create_new_layer("points", "Point")
        layer["features"] = [
            create_point_feature(10, 10, {"id": 1}),
            create_point_feature(100, 100, {"id": 2}),
        ]
        idx, fidx, feat = select_feature([layer], 10, 10, tolerance=5)
        assert feat is not None
        assert feat["properties"]["id"] == 1

    def test_select_miss(self):
        layer = create_new_layer("points", "Point")
        layer["features"] = [create_point_feature(10, 10)]
        idx, fidx, feat = select_feature([layer], 999, 999, tolerance=5)
        assert feat is None

    def test_select_multiline_string(self):
        layer = create_new_layer("roads", "MultiLineString")
        layer["features"] = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [[[0, 0], [10, 0]], [[20, 0], [30, 0]]],
                },
                "properties": {"id": 7},
            }
        ]

        idx, fidx, feat = select_feature([layer], 5, 0, tolerance=1)

        assert (idx, fidx) == (0, 0)
        assert feat["properties"]["id"] == 7

    def test_select_multipolygon(self):
        layer = create_new_layer("parcels", "MultiPolygon")
        layer["features"] = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]],
                        [[[10, 10], [14, 10], [14, 14], [10, 14], [10, 10]]],
                    ],
                },
                "properties": {"id": 8},
            }
        ]

        idx, fidx, feat = select_feature([layer], 12, 12, tolerance=1)

        assert (idx, fidx) == (0, 0)
        assert feat["properties"]["id"] == 8


class TestShapelyCache:
    def test_ensure_cache_creates(self):
        from core.vector_processing import _ensure_shapely_cache, invalidate_shapely_cache

        layer = create_new_layer("test", "Point")
        layer["features"] = [create_point_feature(0, 0), create_point_feature(10, 10)]
        cache = _ensure_shapely_cache(layer)
        assert len(cache) == 2
        assert cache[0] is not None

    def test_cache_reused_on_second_call(self):
        from core.vector_processing import _ensure_shapely_cache

        layer = create_new_layer("test", "Point")
        layer["features"] = [create_point_feature(0, 0)]
        c1 = _ensure_shapely_cache(layer)
        c2 = _ensure_shapely_cache(layer)
        assert c1 is c2  # Same list object

    def test_invalidate_single(self):
        from core.vector_processing import _ensure_shapely_cache, invalidate_shapely_cache

        layer = create_new_layer("test", "Point")
        layer["features"] = [create_point_feature(0, 0), create_point_feature(10, 10)]
        _ensure_shapely_cache(layer)
        invalidate_shapely_cache(layer, 0)
        assert layer["_shapely_cache"][0] is None
        assert layer["_shapely_cache"][1] is not None

    def test_invalidate_all(self):
        from core.vector_processing import _ensure_shapely_cache, invalidate_shapely_cache

        layer = create_new_layer("test", "Point")
        layer["features"] = [create_point_feature(0, 0)]
        _ensure_shapely_cache(layer)
        invalidate_shapely_cache(layer)
        assert layer["_shapely_cache"][0] is None
