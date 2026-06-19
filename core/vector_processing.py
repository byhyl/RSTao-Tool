# core/vector_processing.py
import numpy as np
from shapely.affinity import translate
from shapely.geometry import LineString, Point
from shapely.geometry import Polygon as ShapelyPolygon

from common.exceptions import AlgorithmError
from common.logger import logger


def geojson_to_shapely(geojson_geom):
    """将GeoJSON几何转换为Shapely几何对象"""
    try:
        gtype = geojson_geom["type"]
        if gtype == "Point":
            return Point(geojson_geom["coordinates"])
        elif gtype == "LineString":
            return LineString(geojson_geom["coordinates"])
        elif gtype == "Polygon":
            coords = geojson_geom["coordinates"]
            return ShapelyPolygon(coords[0], coords[1:] if len(coords) > 1 else None)
        elif gtype == "MultiPoint":
            from shapely.geometry import MultiPoint as ShapelyMultiPoint

            return ShapelyMultiPoint(geojson_geom["coordinates"])
        elif gtype == "MultiLineString":
            from shapely.geometry import MultiLineString as ShapelyMultiLineString

            return ShapelyMultiLineString(geojson_geom["coordinates"])
        elif gtype == "MultiPolygon":
            from shapely.geometry import MultiPolygon as ShapelyMultiPolygon

            return ShapelyMultiPolygon(
                [(p[0], p[1:] if len(p) > 1 else None) for p in geojson_geom["coordinates"]]
            )
        else:
            raise AlgorithmError(f"不支持的几何类型: {gtype}")
    except Exception as e:
        logger.error(f"GeoJSON转Shapely失败: {str(e)}", exc_info=True)
        raise AlgorithmError(f"几何转换失败: {str(e)}")


def shapely_to_geojson(shapely_geom):
    """将Shapely几何对象转换为GeoJSON格式"""
    try:
        if isinstance(shapely_geom, Point):
            return {"type": "Point", "coordinates": list(shapely_geom.coords[0])}
        elif isinstance(shapely_geom, LineString):
            return {"type": "LineString", "coordinates": list(shapely_geom.coords)}
        elif isinstance(shapely_geom, ShapelyPolygon):
            rings = [list(shapely_geom.exterior.coords)]
            rings.extend(list(interior.coords) for interior in shapely_geom.interiors)
            return {"type": "Polygon", "coordinates": rings}
        elif hasattr(shapely_geom, "geoms"):
            from shapely.geometry import MultiLineString, MultiPoint, MultiPolygon

            if isinstance(shapely_geom, MultiPoint):
                return {
                    "type": "MultiPoint",
                    "coordinates": [list(p.coords[0]) for p in shapely_geom.geoms],
                }
            elif isinstance(shapely_geom, MultiLineString):
                return {
                    "type": "MultiLineString",
                    "coordinates": [list(ls.coords) for ls in shapely_geom.geoms],
                }
            elif isinstance(shapely_geom, MultiPolygon):
                return {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [list(p.exterior.coords)]
                        + [list(interior.coords) for interior in p.interiors]
                        for p in shapely_geom.geoms
                    ],
                }
        else:
            raise AlgorithmError(f"不支持的几何类型: {type(shapely_geom)}")
    except Exception as e:
        logger.error(f"Shapely转GeoJSON失败: {str(e)}", exc_info=True)
        raise AlgorithmError(f"几何转换失败: {str(e)}")


# ===================== 几何编辑 =====================
def move_feature(feature, dx, dy):
    try:
        logger.debug(f"移动要素: dx={dx:.2f}, dy={dy:.2f}")
        shapely_geom = geojson_to_shapely(feature["geometry"])
        moved_geom = translate(shapely_geom, dx, dy)
        new_feature = feature.copy()
        new_feature["geometry"] = shapely_to_geojson(moved_geom)
        return new_feature
    except Exception as e:
        logger.error(f"移动要素失败: {str(e)}", exc_info=True)
        raise AlgorithmError(f"移动要素失败: {str(e)}")


def create_new_layer(name, geom_type):
    logger.info(f"创建新图层: {name}, 类型: {geom_type}")
    # 标准属性字段
    schema = {
        "geometry": geom_type,
        "properties": {
            "id": "int",
            "name": "str",
            "layer": "str",
            "length": "float",
            "area": "float",
            "remark": "str",
        },
    }
    return {
        "name": name,
        "features": [],
        "visible": True,
        "color": list(np.random.uniform(0.3, 0.8, 3)),
        "cad_color": 5,
        "schema": schema,
        "crs": "EPSG:4326",
    }


def create_point_feature(x, y, template_properties=None):
    props = (
        template_properties.copy()
        if template_properties
        else {"id": 0, "name": "", "layer": "POINT", "length": 0.0, "area": 0.0, "remark": ""}
    )
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [x, y]},
        "properties": props,
    }


def create_line_feature(points, template_properties=None):
    length_val = LineString(points).length  # ✅ 直接用对象属性，无需导入
    props = (
        template_properties.copy()
        if template_properties
        else {
            "id": 0,
            "name": "",
            "layer": "LINE",
            "length": round(length_val, 2),
            "area": 0.0,
            "remark": "",
        }
    )
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": points},
        "properties": props,
    }


def create_polygon_feature(points, template_properties=None):
    closed_points = points + [points[0]]
    poly = ShapelyPolygon(closed_points)
    length_val = round(poly.length, 2)  # ✅ 直接用对象属性
    area_val = round(poly.area, 2)
    props = (
        template_properties.copy()
        if template_properties
        else {
            "id": 0,
            "name": "",
            "layer": "POLYGON",
            "length": length_val,
            "area": area_val,
            "remark": "",
        }
    )
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [closed_points]},
        "properties": props,
    }


# ===================== Shapely 几何缓存 =====================
def _ensure_shapely_cache(layer):
    """确保图层拥有与 features 同步的 Shapely 缓存。"""
    if "_shapely_cache" not in layer:
        layer["_shapely_cache"] = [None] * len(layer["features"])
    cache = layer["_shapely_cache"]
    features = layer["features"]
    if len(cache) != len(features):
        layer["_shapely_cache"] = [None] * len(features)
        cache = layer["_shapely_cache"]
    for i, feat in enumerate(features):
        if cache[i] is None:
            try:
                cache[i] = geojson_to_shapely(feat["geometry"])
            except Exception:
                cache[i] = Point(0, 0)
    return cache


def invalidate_shapely_cache(layer, feature_index=None):
    """使 Shapely 缓存失效；feature_index=None 表示重置整个图层。"""
    if "_shapely_cache" not in layer:
        return
    if feature_index is None:
        layer["_shapely_cache"] = [None] * len(layer["features"])
    elif 0 <= feature_index < len(layer["_shapely_cache"]):
        layer["_shapely_cache"][feature_index] = None


def select_feature(layers, x, y, tolerance=5):
    try:
        for layer_idx, layer in reversed(list(enumerate(layers))):
            if not layer["visible"]:
                continue
            cache = _ensure_shapely_cache(layer)
            for feat_idx, feature in enumerate(layer["features"]):
                shapely_geom = cache[feat_idx]
                if shapely_geom.distance(Point(x, y)) < tolerance:
                    return layer_idx, feat_idx, feature
        return None, None, None
    except Exception as e:
        logger.error(f"选择要素失败: {str(e)}", exc_info=True)
        raise AlgorithmError(f"选择要素失败: {str(e)}")


# ===================== 属性表编辑算法 =====================
def update_feature_property(feature, field_name, value):
    try:
        new_feature = feature.copy()
        new_feature["properties"] = feature.get("properties", {}).copy()
        new_feature["properties"][field_name] = value
        return new_feature
    except Exception as e:
        raise AlgorithmError(f"更新属性失败: {str(e)}")


def add_property_field(layer, field_name, field_type="str"):
    try:
        layer["schema"]["properties"][field_name] = field_type
        default_val = "" if field_type == "str" else 0
        for feat in layer["features"]:
            feat["properties"][field_name] = default_val
        return layer
    except Exception as e:
        raise AlgorithmError(f"新增字段失败: {str(e)}")


def delete_property_field(layer, field_name):
    try:
        if field_name not in layer["schema"]["properties"]:
            raise AlgorithmError("字段不存在")
        del layer["schema"]["properties"][field_name]
        for feat in layer["features"]:
            if field_name in feat["properties"]:
                del feat["properties"][field_name]
        return layer
    except Exception as e:
        raise AlgorithmError(f"删除字段失败: {str(e)}")


# ===================== 批量编辑属性 =====================
def batch_update_properties(layer, field_name, value):
    try:
        for feat in layer["features"]:
            feat["properties"][field_name] = value
        return layer
    except Exception as e:
        raise AlgorithmError(f"批量更新属性失败: {str(e)}")
