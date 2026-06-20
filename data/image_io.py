from pathlib import Path

import cv2
import numpy as np

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
        axes = getattr(page, "axes", "")
        samples = int(getattr(page, "samplesperpixel", 0) or 0)

        if image.ndim == 3:
            first_axis_is_sample = (
                bool(axes)
                and axes[0] in {"S", "C"}
                and axes[-1]
                not in {
                    "S",
                    "C",
                }
            )
            shape_matches_samples = samples > 0 and image.shape[0] == samples
            looks_band_first = image.shape[0] in (1, 2, 3, 4) and image.shape[-1] not in (
                1,
                2,
                3,
                4,
            )
            if first_axis_is_sample or shape_matches_samples or looks_band_first:
                image = np.moveaxis(image, 0, -1)

        # 处理多波段
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            if image.dtype != np.uint8:
                image = _normalize_to_uint8(image)
        elif image.ndim == 3:
            bands = image.shape[2]
            if bands >= 3:
                image = image[:, :, :3]
            elif bands == 2:
                image = cv2.cvtColor(image[:, :, 0], cv2.COLOR_GRAY2RGB)
            elif bands == 1:
                image = cv2.cvtColor(image[:, :, 0], cv2.COLOR_GRAY2RGB)
            if image.dtype != np.uint8:
                image = _normalize_to_uint8(image)
        # 缓存地理信息
        _geo_cache.update(_extract_geo_info(tif))
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
    else:
        img = np.zeros_like(img, dtype=np.uint8)
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


def get_image_metadata(file_path):
    """Return lightweight image metadata without loading full pixel data when possible."""
    path = Path(str(file_path))
    if not path.exists():
        raise FileReadError(f"影像文件不存在: {file_path}")

    meta = {
        "path": str(path),
        "name": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 3),
        "width": 0,
        "height": 0,
        "bands": 0,
        "dtype": "",
        "driver": "",
        "crs": "",
        "epsg": None,
        "bounds": None,
        "pixel_size": None,
    }

    ext = path.suffix.lower()
    if ext in (".tif", ".tiff", ".img", ".jp2", ".vrt"):
        try:
            import rasterio

            with rasterio.open(path) as ds:
                meta.update(
                    {
                        "width": ds.width,
                        "height": ds.height,
                        "bands": ds.count,
                        "dtype": ds.dtypes[0] if ds.dtypes else "",
                        "driver": ds.driver,
                        "crs": str(ds.crs) if ds.crs else "",
                        "epsg": ds.crs.to_epsg() if ds.crs else None,
                        "bounds": tuple(ds.bounds) if ds.bounds else None,
                        "pixel_size": (
                            (abs(ds.transform.a), abs(ds.transform.e)) if ds.transform else None
                        ),
                    }
                )
                return meta
        except Exception:
            pass

    if ext in (".tif", ".tiff"):
        try:
            import tifffile

            with tifffile.TiffFile(path) as tif:
                page = tif.pages[0]
                shape = page.shape
                meta["driver"] = "TIFF"
                meta["dtype"] = str(page.dtype)
                if len(shape) == 2:
                    meta["height"], meta["width"] = shape
                    meta["bands"] = 1
                elif len(shape) >= 3:
                    meta["height"], meta["width"] = shape[0], shape[1]
                    meta["bands"] = shape[2]
                return meta
        except Exception:
            pass

    try:
        from PIL import Image

        with Image.open(path) as im:
            meta.update(
                {
                    "width": im.width,
                    "height": im.height,
                    "bands": len(im.getbands()),
                    "dtype": str(np.asarray(im).dtype),
                    "driver": im.format or "",
                }
            )
            return meta
    except Exception as e:
        logger.error(f"读取影像元数据失败: {str(e)}", exc_info=True)
        raise FileReadError(f"读取影像元数据失败: {str(e)}")


def read_raster_profile(file_path):
    """Read a rasterio profile for geospatial save/export workflows."""
    try:
        import rasterio

        with rasterio.open(file_path) as src:
            profile = src.profile.copy()
            profile["crs"] = src.crs
            profile["transform"] = src.transform
            profile["bounds"] = tuple(src.bounds) if src.bounds else None
            profile["width"] = src.width
            profile["height"] = src.height
            return profile
    except ImportError as exc:
        raise FileReadError("rasterio is required for GeoTIFF metadata.") from exc
    except Exception as exc:
        logger.error(f"Read raster profile failed: {exc}", exc_info=True)
        raise FileReadError(f"Read raster profile failed: {exc}") from exc


def read_raster_data(file_path, bands=None, preserve_dtype=True):
    """Read raster pixels for processing without forcing 8-bit preview conversion."""
    path = Path(str(file_path))
    ext = path.suffix.lower()
    try:
        if ext in (".tif", ".tiff", ".img", ".jp2", ".vrt"):
            try:
                import rasterio

                with rasterio.open(path) as src:
                    indexes = bands or list(range(1, src.count + 1))
                    arr = src.read(indexes)
                    arr = np.moveaxis(arr, 0, -1)
                    if arr.shape[2] == 1:
                        arr = arr[:, :, 0]
                    if not preserve_dtype:
                        arr = make_preview(arr)
                    return arr
            except ImportError:
                logger.warning("rasterio 未安装，降级为预览读取: %s", file_path)
            except Exception as exc:
                logger.warning("rasterio 读取失败，降级为通用影像读取: %s", exc)

        image = read_image(str(path))
        return image if preserve_dtype else make_preview(image)
    except FileReadError:
        raise
    except Exception as exc:
        logger.error(f"读取处理影像失败: {exc}", exc_info=True)
        raise FileReadError(f"读取处理影像失败: {exc}") from exc


def make_preview(image, low_percent=2, high_percent=98):
    """Create an RGB/gray uint8 preview from arbitrary dtype image data."""
    arr = np.asarray(image)
    if arr.ndim == 2:
        return _preview_band(arr, low_percent, high_percent)
    if arr.ndim == 3:
        if arr.shape[2] == 1:
            return _preview_band(arr[:, :, 0], low_percent, high_percent)
        bands = min(arr.shape[2], 3)
        return np.dstack(
            [_preview_band(arr[:, :, i], low_percent, high_percent) for i in range(bands)]
        )
    raise FileReadError("影像预览仅支持二维或三维数组")


def _preview_band(band, low_percent=2, high_percent=98):
    arr = np.asarray(band)
    if arr.dtype == np.uint8:
        return arr
    arr = arr.astype(np.float32)
    low = float(np.nanpercentile(arr, low_percent))
    high = float(np.nanpercentile(arr, high_percent))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.zeros(arr.shape, dtype=np.uint8)
    return np.clip((arr - low) / (high - low) * 255, 0, 255).astype(np.uint8)


def save_geotiff_like(source_path, image, output_path, color_order="BGR"):
    """Save a result image as GeoTIFF while preserving georeference from source_path."""
    try:
        import rasterio

        arr = _prepare_geotiff_array(image, color_order=color_order)
        count, height, width = arr.shape

        with rasterio.open(source_path) as src:
            profile = src.profile.copy()
            profile.update(
                driver="GTiff",
                height=height,
                width=width,
                count=count,
                dtype=str(arr.dtype),
                crs=src.crs,
                transform=src.transform,
            )
            profile.setdefault("compress", "deflate")
            _sanitize_nodata(profile, arr.dtype)

            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(arr)
        return True
    except ImportError as exc:
        raise FileWriteError("rasterio is required to save GeoTIFF results.") from exc
    except Exception as exc:
        logger.error(f"Save GeoTIFF failed: {exc}", exc_info=True)
        raise FileWriteError(f"Save GeoTIFF failed: {exc}") from exc


def save_raster_result(source_path, image, output_path, color_order="RGB"):
    """Save processing output, preserving GeoTIFF metadata when possible."""
    out_ext = Path(str(output_path)).suffix.lower()
    src_ext = Path(str(source_path)).suffix.lower() if source_path else ""
    if out_ext in (".tif", ".tiff") and src_ext in (".tif", ".tiff", ".img", ".jp2", ".vrt"):
        return save_geotiff_like(source_path, image, output_path, color_order=color_order)
    return save_image(
        make_preview(image) if np.asarray(image).dtype != np.uint8 else image, output_path
    )


def _prepare_geotiff_array(image, color_order="BGR"):
    arr = np.asarray(image)
    if arr.ndim == 2:
        return arr[np.newaxis, :, :]
    if arr.ndim != 3:
        raise FileWriteError("GeoTIFF export expects a 2D or 3D image array.")

    if arr.shape[2] >= 3 and color_order.upper() == "BGR":
        arr = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_BGR2RGB)
    elif arr.shape[2] > 4:
        arr = arr[:, :, :4]

    return np.moveaxis(np.ascontiguousarray(arr), -1, 0)


def _sanitize_nodata(profile, dtype):
    nodata = profile.get("nodata")
    if nodata is None:
        return
    try:
        np.array([nodata], dtype=dtype)
    except Exception:
        profile.pop("nodata", None)


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
        if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"):
            ext = ".png"
        cv2.imencode(ext, image)[1].tofile(str(file_path))
        return True
    except Exception as e:
        logger.error(f"保存影像失败: {str(e)}", exc_info=True)
        raise FileWriteError(f"保存影像失败: {str(e)}")
