import cv2
import numpy as np
from pathlib import Path

from common.exceptions import FileReadError, FileWriteError
from common.logger import logger


def read_image(file_path):
    """
    读取影像文件，统一返回RGB格式的numpy数组
    支持: jpg, png, bmp, tif, tiff, GeoTIFF 等常见格式
    """
    try:
        file_path = str(file_path)
        logger.info(f"读取影像: {file_path}")
        ext = Path(file_path).suffix.lower()

        # GeoTIFF / TIFF 使用 tifffile 读取以保留地理信息
        if ext in (".tif", ".tiff"):
            return _read_tiff(file_path)

        image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FileReadError(f"无法读取影像文件: {file_path}")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    except FileReadError:
        raise
    except Exception as e:
        logger.error(f"读取影像失败: {str(e)}", exc_info=True)
        raise FileReadError(f"读取影像失败: {str(e)}")


def _read_tiff(file_path):
    """读取 TIFF/GeoTIFF，保留地理参考信息"""
    try:
        import tifffile
    except ImportError:
        logger.warning("tifffile 未安装，使用 OpenCV 降级读取 TIFF")
        image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FileReadError(f"无法读取影像文件: {file_path}")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    with tifffile.TiffFile(file_path) as tif:
        page = tif.pages[0]
        image = page.asarray()
        # 处理多波段
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.ndim == 3 and image.shape[2] >= 3:
            image = image[:, :, :3]  # 取前3个波段
            if image.dtype != np.uint8:
                image = _normalize_to_uint8(image)
        # 缓存地理信息
        _last_geo_info = _extract_geo_info(tif)
    return image


# 全局缓存最近一次读取的 GeoTIFF 地理信息
_geo_cache = {}


def _normalize_to_uint8(img):
    """将非 uint8 图像归一化到 0-255"""
    if img.dtype == np.uint8:
        return img
    img_min, img_max = img.min(), img.max()
    if img_max > img_min:
        img = ((img - img_min) / (img_max - img_min) * 255).astype(np.uint8)
    return img


def _extract_geo_info(tif):
    """从 TIFF 提取地理参考信息"""
    info = {"crs": None, "transform": None, "bounds": None, "tags": {}}
    try:
        page = tif.pages[0]
        for tag in page.tags.values():
            info["tags"][tag.name] = tag.value

        # 尝试获取地理标签
        geo_keys = {tag.name: tag.value for tag in page.tags.values()}
        if "ModelTiepointTag" in geo_keys:
            info["tie_points"] = geo_keys["ModelTiepointTag"]
        if "ModelPixelScaleTag" in geo_keys:
            info["pixel_scale"] = geo_keys["ModelPixelScaleTag"]
        if "GTModelTypeGeoKey" in geo_keys:
            info["model_type"] = geo_keys["GTModelTypeGeoKey"]
    except Exception:
        pass
    return info


def get_geotiff_info(file_path=None):
    """
    获取 GeoTIFF 地理参考信息
    如果提供路径，读取该文件；否则返回上次读取的缓存
    """
    if file_path:
        _read_tiff(str(file_path))
    return _geo_cache.copy()


def read_geotiff_with_geo(file_path):
    """读取 GeoTIFF 并同时返回图像和地理信息"""
    image = read_image(str(file_path))
    return image, _geo_cache.copy()


def save_image(image, file_path):
    """保存影像文件，自动处理中文路径"""
    try:
        logger.info(f"保存影像: {file_path}")
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        ext = Path(str(file_path)).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".bmp"):
            ext = ".jpg"
        cv2.imencode(ext, image)[1].tofile(str(file_path))
        return True
    except Exception as e:
        logger.error(f"保存影像失败: {str(e)}", exc_info=True)
        raise FileWriteError(f"保存影像失败: {str(e)}")