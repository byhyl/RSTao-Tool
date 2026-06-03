# data/vector_io.py
import fiona
import ezdxf
from common.logger import logger
from common.exceptions import FileReadError, FileWriteError

def read_shp(file_path):
    try:
        logger.info(f"读取矢量: {file_path}")
        with fiona.open(file_path, 'r', encoding='utf-8') as src:
            features = list(src)
            schema = src.schema
            crs = src.crs
            return {
                "features": features,
                "schema": schema,
                "crs": crs,
                "name": file_path.split('/')[-1].split('\\')[-1].split('.')[0]
            }
    except Exception as e:
        logger.error(f"读取矢量失败: {str(e)}", exc_info=True)
        raise FileReadError(f"读取矢量失败: {str(e)}")

def save_shp(data, file_path):
    try:
        logger.info(f"保存SHP: {file_path}")
        with fiona.open(
            file_path, 'w', driver='ESRI Shapefile',
            schema=data['schema'], crs=data['crs'], encoding='utf-8'
        ) as dst:
            dst.writerecords(data['features'])
        return True
    except Exception as e:
        logger.error(f"保存SHP失败: {str(e)}", exc_info=True)
        raise FileWriteError(f"保存SHP失败: {str(e)}")

# ===================== ✅【新增】导出标准CAD样式DWG/DXF =====================
def save_dwg(data, file_path):
    try:
        logger.info(f"保存DWG/DXF: {file_path}")
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        doc.layers.new(name=data['name'], dxfattribs={"color": data.get("cad_color", 5)})

        for feat in data['features']:
            geom = feat['geometry']
            props = feat.get('properties', {})
            layer_name = props.get('layer', data['name'])

            if geom['type'] == "Point":
                x, y = geom['coordinates']
                msp.add_point((x, y), dxfattribs={"layer": layer_name})

            elif geom['type'] == "LineString":
                pts = [(p[0], p[1]) for p in geom['coordinates']]
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name})

            elif geom['type'] == "Polygon":
                pts = [(p[0], p[1]) for p in geom['coordinates'][0]]
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name, "closed": True})

        doc.saveas(file_path)
        return True
    except Exception as e:
        logger.error(f"保存DWG失败: {str(e)}", exc_info=True)
        raise FileWriteError(f"保存DWG失败: {str(e)}")