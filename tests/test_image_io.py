"""Image IO metadata tests."""

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.image_io import get_image_metadata, read_image, save_geotiff_like


def test_get_image_metadata_png(tmp_path):
    image_path = tmp_path / "sample.png"
    arr = np.zeros((12, 10, 3), dtype=np.uint8)
    Image.fromarray(arr).save(image_path)

    meta = get_image_metadata(image_path)

    assert meta["width"] == 10
    assert meta["height"] == 12
    assert meta["bands"] == 3
    assert meta["dtype"] == "uint8"
    assert meta["size_bytes"] > 0


def test_read_tiff_band_first_rgb(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    image_path = tmp_path / "band_first.tif"
    arr = np.zeros((3, 4, 5), dtype=np.uint8)
    arr[0, :, :] = 10
    arr[1, :, :] = 20
    arr[2, :, :] = 30
    tifffile.imwrite(image_path, arr, photometric="rgb", planarconfig="separate")

    image = read_image(image_path)

    assert image.shape == (4, 5, 3)
    assert image[0, 0].tolist() == [10, 20, 30]


def test_save_geotiff_like_preserves_spatial_reference(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    source = tmp_path / "source.tif"
    output = tmp_path / "result.tif"
    transform = from_origin(100, 200, 2, 2)
    data = np.zeros((1, 4, 5), dtype=np.uint8)

    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        height=4,
        width=5,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)

    image = np.zeros((4, 5, 3), dtype=np.uint8)
    image[:, :, 2] = 255

    assert save_geotiff_like(source, image, output, color_order="BGR")

    with rasterio.open(output) as dst:
        assert dst.crs.to_epsg() == 4326
        assert dst.transform == transform
        assert dst.count == 3
        assert dst.read(1)[0, 0] == 255
