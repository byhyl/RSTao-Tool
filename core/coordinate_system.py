"""坐标系转换模块 — EPSG + 7参数 Bursa-Wolf + 文件解析"""

import csv
import io
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from common.logger import logger

# ====================== 常用 EPSG 定义 ======================
COMMON_EPSG = {
    "WGS84": 4326,
    "CGCS2000": 4490,
    "Beijing54": 4214,
    "Xian80": 4610,
    "Web Mercator": 3857,
    "UTM Zone 50N": 32650,
    "UTM Zone 51N": 32651,
}

CHINA_EPSG = {
    "北京54 / 3度 114E": 2401,
    "北京54 / 3度 117E": 2402,
    "北京54 / 6度 18N": 2327,
    "西安80 / 3度 114E": 2362,
    "西安80 / 3度 117E": 2363,
    "西安80 / 6度 18N": 2332,
    "CGCS2000 / 3度 114E": 4525,
    "CGCS2000 / 3度 117E": 4526,
    "CGCS2000 / 6度 18N": 4493,
}


@dataclass
class SevenParams:
    """7参数 Bursa-Wolf 模型"""

    dx: float = 0.0  # 平移 X (m)
    dy: float = 0.0  # 平移 Y (m)
    dz: float = 0.0  # 平移 Z (m)
    rx: float = 0.0  # 旋转 X (arcsec)
    ry: float = 0.0  # 旋转 Y (arcsec)
    rz: float = 0.0  # 旋转 Z (arcsec)
    scale: float = 0.0  # 尺度因子 (ppm)

    def to_matrix(self) -> np.ndarray:
        """转换为 4x4 变换矩阵"""
        sec_to_rad = math.pi / (180.0 * 3600.0)
        ppm_to_scale = 1.0 + self.scale * 1e-6
        rx, ry, rz = self.rx * sec_to_rad, self.ry * sec_to_rad, self.rz * sec_to_rad
        R = (
            np.array(
                [
                    [1, -rz, ry],
                    [rz, 1, -rx],
                    [-ry, rx, 1],
                ]
            )
            * ppm_to_scale
        )
        T = np.array([[self.dx], [self.dy], [self.dz]])
        M = np.eye(4)
        M[:3, :3] = R
        M[:3, 3:4] = T
        return M

    @classmethod
    def preset(cls, name: str) -> "SevenParams":
        """常用预设参数"""
        presets = {
            "WGS84_to_CGCS2000": cls(dx=0, dy=0, dz=0, rx=0, ry=0, rz=0, scale=0),
            "BJ54_to_WGS84": cls(dx=-22.0, dy=118.0, dz=30.5, rx=0, ry=0, rz=0, scale=0),
            "XA80_to_WGS84": cls(dx=-10.0, dy=103.0, dz=35.0, rx=0, ry=0, rz=0, scale=0),
        }
        return presets.get(name, cls())


@dataclass
class CoordinateTransform:
    src_epsg: int
    dst_epsg: int
    src_name: str = ""
    dst_name: str = ""
    seven_params: Optional[SevenParams] = None


@dataclass
class PointSet:
    """点集"""

    points: List[Tuple[float, float]] = field(default_factory=list)
    names: List[str] = field(default_factory=list)
    source_file: str = ""


@dataclass
class RasterInfo:
    """栅格影像信息"""

    path: str = ""
    width: int = 0
    height: int = 0
    bands: int = 0
    crs: str = ""
    epsg: int = 0
    bounds: Tuple[float, float, float, float] = (0, 0, 0, 0)
    pixel_size: Tuple[float, float] = (1.0, 1.0)


class CoordinateSystem:
    """坐标系管理器"""

    def __init__(self):
        self._pyproj_available = False
        self._rasterio_available = False
        try:
            from pyproj import CRS, Transformer

            self._Transformer = Transformer
            self._CRS = CRS
            self._pyproj_available = True
        except ImportError:
            logger.warning("pyproj 未安装，坐标系转换功能受限")
        try:
            import rasterio

            self._rasterio_available = True
        except ImportError:
            pass

    @property
    def available(self) -> bool:
        return self._pyproj_available

    @staticmethod
    def list_all() -> dict:
        return {**COMMON_EPSG, **CHINA_EPSG}

    # ---- 点坐标转换 ----
    def transform_point(
        self, x: float, y: float, src_epsg: int, dst_epsg: int, params: SevenParams = None
    ) -> Optional[Tuple[float, float]]:
        if not self._pyproj_available:
            return None
        try:
            if params and any(
                [params.dx, params.dy, params.dz, params.rx, params.ry, params.rz, params.scale]
            ):
                return self._transform_7param(x, y, params)
            transformer = self._Transformer.from_crs(
                f"EPSG:{src_epsg}", f"EPSG:{dst_epsg}", always_xy=True
            )
            return transformer.transform(x, y)
        except Exception as e:
            logger.error(f"坐标转换失败: {e}")
            return None

    def transform_points(
        self,
        points: List[Tuple[float, float]],
        src_epsg: int,
        dst_epsg: int,
        params: SevenParams = None,
    ) -> List[Tuple[float, float]]:
        if not points:
            return []
        if not self._pyproj_available:
            return points
        try:
            if params and any(
                [params.dx, params.dy, params.dz, params.rx, params.ry, params.rz, params.scale]
            ):
                return [self._transform_7param(x, y, params) for x, y in points]
            transformer = self._Transformer.from_crs(
                f"EPSG:{src_epsg}", f"EPSG:{dst_epsg}", always_xy=True
            )
            xs, ys = zip(*points)
            lons, lats = transformer.transform(xs, ys)
            return list(zip(lons, lats))
        except Exception as e:
            logger.error(f"批量转换失败: {e}")
            return points

    def _transform_7param(
        self, x: float, y: float, params: SevenParams, src_elev: float = 0
    ) -> Tuple[float, float]:
        """7参数 Bursa-Wolf 变换 (WGS84 经纬度 → 目标坐标系)"""
        # 先将经纬度转为地心直角坐标
        a, f = 6378137.0, 1.0 / 298.257223563
        e2 = 2 * f - f * f
        lat, lon = math.radians(y), math.radians(x)
        N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        X = (N + src_elev) * math.cos(lat) * math.cos(lon)
        Y = (N + src_elev) * math.cos(lat) * math.sin(lon)
        Z = (N * (1 - e2) + src_elev) * math.sin(lat)

        # 7参数变换
        M = params.to_matrix()
        xyz = np.array([[X], [Y], [Z], [1.0]])
        xyz_t = M @ xyz
        Xt, Yt, Zt = xyz_t[0, 0], xyz_t[1, 0], xyz_t[2, 0]

        # 地心直角坐标 → 经纬度
        lon_t = math.degrees(math.atan2(Yt, Xt))
        p = math.sqrt(Xt**2 + Yt**2)
        lat_t = math.degrees(math.atan2(Zt, p * (1 - e2)))
        return (lon_t, lat_t)

    # ---- 栅格影像 CRS 读取 ----
    def read_raster_info(self, path: str) -> Optional[RasterInfo]:
        """读取影像坐标系信息"""
        info = RasterInfo(path=path)
        if self._rasterio_available:
            try:
                import rasterio

                with rasterio.open(path) as ds:
                    info.width, info.height = ds.width, ds.height
                    info.bands = ds.count
                    info.crs = str(ds.crs)
                    info.bounds = ds.bounds
                    info.pixel_size = ds.res
                    if ds.crs and ds.crs.to_epsg():
                        info.epsg = ds.crs.to_epsg()
            except Exception as e:
                logger.warning(f"rasterio 读取失败: {e}")
        # Fallback: try tifffile
        if not info.width:
            try:
                import tifffile

                with tifffile.TiffFile(path) as tif:
                    page = tif.pages[0]
                    info.width, info.height = page.shape[1], page.shape[0]
                    info.bands = page.samplesperpixel if hasattr(page, "samplesperpixel") else 1
                    # Try to read GeoKeyDirectoryTag
                    for tag in tif.pages[0].tags.values():
                        if hasattr(tag, "name") and "GeoKey" in str(tag.name):
                            info.crs = f"GeoTIFF tags found (EPSG unknown)"
            except Exception as e:
                logger.warning(f"tifffile 读取失败: {e}")
        # Try Pillow
        if not info.width:
            try:
                from PIL import Image

                Image.MAX_IMAGE_PIXELS = None
                with Image.open(path) as im:
                    info.width, info.height = im.size
                    info.bands = len(im.getbands())
                    exif = im.getexif()
                    # 尝试读取 GeoTIFF 标签
                    for k, v in exif.items() if exif else []:
                        if k in (34735, 34736, 34737):
                            info.crs = f"GeoTIFF GeoKey: {k}"
            except Exception:
                pass
        return info

    # ---- 点文件解析 ----
    def parse_point_file(self, path: str) -> Optional[PointSet]:
        """解析点文件 (CSV/TXT)"""
        ps = PointSet(source_file=path)
        ext = Path(path).suffix.lower()
        try:
            if ext == ".csv":
                return self._parse_csv(path, ps)
            elif ext in (".txt", ".xy", ".pts"):
                return self._parse_txt(path, ps)
            else:
                return self._parse_txt(path, ps)
        except Exception as e:
            logger.error(f"解析点文件失败: {e}")
            return None

    def _parse_csv(self, path: str, ps: PointSet) -> PointSet:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return ps

        x_names = {"x", "lon", "longitude", "easting", "东坐标", "经度"}
        y_names = {"y", "lat", "latitude", "northing", "北坐标", "纬度"}
        name_names = {"name", "id", "point", "点名", "名称", "编号"}

        header = [cell.strip().lower() for cell in rows[0]]
        x_idx = next((i for i, value in enumerate(header) if value in x_names), None)
        y_idx = next((i for i, value in enumerate(header) if value in y_names), None)
        name_idx = next((i for i, value in enumerate(header) if value in name_names), None)

        has_header = x_idx is not None and y_idx is not None
        data_rows = rows[1:] if has_header else rows
        if not has_header:
            x_idx, y_idx = 0, 1
            name_idx = 2

        for i, row in enumerate(data_rows):
            if len(row) <= max(x_idx, y_idx):
                continue
            try:
                ps.points.append((float(row[x_idx]), float(row[y_idx])))
                if name_idx is not None and len(row) > name_idx and row[name_idx].strip():
                    ps.names.append(row[name_idx].strip())
                else:
                    ps.names.append(f"P{i+1}")
            except ValueError:
                continue
        return ps

    def _parse_txt(self, path: str, ps: PointSet) -> PointSet:
        with open(path, "r", encoding="utf-8-sig") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.replace(",", " ").replace("\t", " ").split()
                if len(parts) >= 2:
                    try:
                        x, y = float(parts[0]), float(parts[1])
                        ps.points.append((x, y))
                        ps.names.append(parts[2] if len(parts) > 2 else f"P{i+1}")
                    except ValueError:
                        continue
        return ps

    def export_points_csv(
        self,
        points: List[Tuple[float, float]],
        path: str,
        src_epsg: int,
        dst_epsg: int,
        names: List[str] = None,
    ):
        """导出转换后的点集为 CSV"""
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Src_X", "Src_Y", "Dst_X", "Dst_Y"])
            names = names or [f"P{i+1}" for i in range(len(points))]
            for i, (sx, sy) in enumerate(points):
                result = self.transform_point(sx, sy, src_epsg, dst_epsg)
                if result is None:
                    continue
                dx, dy = result
                writer.writerow([names[i], sx, sy, dx, dy])

    def wgs84_to_projection(
        self, lon: float, lat: float, dst_epsg: int
    ) -> Optional[Tuple[float, float]]:
        return self.transform_point(lon, lat, 4326, dst_epsg)

    def projection_to_wgs84(
        self, x: float, y: float, src_epsg: int
    ) -> Optional[Tuple[float, float]]:
        return self.transform_point(x, y, src_epsg, 4326)

    def auto_detect_utm(self, lon: float, lat: float) -> int:
        zone = int((lon + 180) / 6) + 1
        return 32600 + zone if lat >= 0 else 32700 + zone
