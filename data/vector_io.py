from common.exceptions import FileReadError, FileWriteError
from common.logger import logger


def _require_fiona():
    try:
        import fiona

        return fiona
    except ImportError as exc:
        raise FileReadError("读取/保存 SHP 需要安装 fiona。") from exc


def _require_ezdxf():
    try:
        import ezdxf

        return ezdxf
    except ImportError as exc:
        raise FileWriteError("导出 DWG/DXF 需要安装 ezdxf。") from exc


def read_shp(file_path):
    try:
        fiona = _require_fiona()
        logger.info(f"读取矢量: {file_path}")
        with fiona.open(file_path, "r", encoding="utf-8") as src:
            features = list(src)
            schema = src.schema
            crs = src.crs
            return {
                "features": features,
                "schema": schema,
                "crs": crs,
                "name": file_path.split("/")[-1].split("\\")[-1].split(".")[0],
            }
    except Exception as e:
        logger.error(f"读取矢量失败: {str(e)}", exc_info=True)
        raise FileReadError(f"读取矢量失败: {str(e)}")


def save_shp(data, file_path):
    try:
        fiona = _require_fiona()
        logger.info(f"保存SHP: {file_path}")
        with fiona.open(
            file_path,
            "w",
            driver="ESRI Shapefile",
            schema=data["schema"],
            crs=data["crs"],
            encoding="utf-8",
        ) as dst:
            dst.writerecords(data["features"])
        return True
    except Exception as e:
        logger.error(f"保存SHP失败: {str(e)}", exc_info=True)
        raise FileWriteError(f"保存SHP失败: {str(e)}")


def save_dwg(data, file_path):
    try:
        ezdxf = _require_ezdxf()
        logger.info(f"保存DWG/DXF: {file_path}")
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        doc.layers.new(name=data["name"], dxfattribs={"color": data.get("cad_color", 5)})

        for feat in data["features"]:
            geom = feat["geometry"]
            props = feat.get("properties", {})
            layer_name = props.get("layer", data["name"])

            if geom["type"] == "Point":
                x, y = geom["coordinates"]
                msp.add_point((x, y), dxfattribs={"layer": layer_name})

            elif geom["type"] == "LineString":
                pts = [(p[0], p[1]) for p in geom["coordinates"]]
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name})

            elif geom["type"] == "Polygon":
                pts = [(p[0], p[1]) for p in geom["coordinates"][0]]
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name, "closed": True})

            elif geom["type"] == "MultiPoint":
                for pt in geom["coordinates"]:
                    msp.add_point((pt[0], pt[1]), dxfattribs={"layer": layer_name})

            elif geom["type"] == "MultiLineString":
                for line in geom["coordinates"]:
                    pts = [(p[0], p[1]) for p in line]
                    msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name})

            elif geom["type"] == "MultiPolygon":
                for poly in geom["coordinates"]:
                    pts = [(p[0], p[1]) for p in poly[0]]
                    msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name, "closed": True})

        doc.saveas(file_path)
        return True
    except Exception as e:
        logger.error(f"保存DWG失败: {str(e)}", exc_info=True)
        raise FileWriteError(f"保存DWG失败: {str(e)}")
